"""Shared by every pipeline step: the @node wrapper (announces each step and fails closed), the helpers
that record findings, and the constants and prompts the steps use."""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps

from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from ap_agent.ai.gateway import AiUnavailable, InvalidModelOutput
from ap_agent.checks.framework import CheckContext, LinePair, run_checks
from ap_agent.classify.document import NON_PAYABLE, NOTES, classify_document
from ap_agent.classify.transaction import classify_transaction
from ap_agent.core.models import Finding, Invoice, Outcome, ParseBlock, Status
from ap_agent.core.money import fmt_inr
from ap_agent.decision.engine import (accept_escalation, completeness_guard, compose_verdict, escalation_finding,
                                      floor)
from ap_agent.reading.extract import EXTRACT_SCHEMA, build_extract_messages, to_invoice
from ap_agent.reading.ground import ground
from ap_agent.reading.parse import parse_blocks
from ap_agent.reading.render import render_pages
from ap_agent.reading.text_layer import text_layer
from ap_agent.rulebook.loader import load_aop, render_reason
from ap_agent.rules.normalise import normal_invoice_no, parse_date_in, parse_inr

TXN_LABELS = {"standard_po": "Standard PO", "recurring": "Recurring", "po_less": "PO-less"}
DOC_LABELS = {"proforma": "proforma invoice", "quotation": "quotation", "statement": "statement of account",
              "other": "document that is not an invoice", "credit_note": "credit note", "debit_note": "debit note"}
from ap_agent.decision.review import REVIEW_SCHEMA, REVIEW_SYSTEM, review_message  # noqa: E402,F401
HUMAN_CODES = {"approve_anyway": "APPROVED_BY_PERSON", "sign_off": "SIGNED_OFF", "reject": "REJECTED_BY_PERSON"}


# ---------- helpers ----------

def findings_of(state) -> list[Finding]:
    return [Finding.model_validate(f) for f in state.get("findings", [])]


def invoice_of(state) -> Invoice:
    return Invoice.model_validate(state["invoice"]) if state.get("invoice") else Invoice()


def _dump(inv: Invoice) -> dict:
    return inv.model_dump(mode="json")


def _cache(state, name: str) -> str | None:
    return f"{state['sample_id']}/{name}" if state.get("sample_id") else None


def _record(deps, state, new: list[Finding]) -> list[dict]:
    out = list(state.get("findings", []))
    for f in new:
        deps.store.add_finding(state["case_id"], f)
        deps.bus.publish(state["case_id"], "finding", f.model_dump(mode="json"))
        out.append(f.model_dump(mode="json"))
    return out


def _finding(aop, code: str, title: str, check: str, stage: str, data: dict | None = None, stop: bool = False,
             status: Status | None = None) -> Finding:
    r = aop.reasons[code]
    return Finding(check=check, stage=stage, status=status or (Status.WARN if r.outcome is None else Status.FAIL),
                   code=code, outcome=r.outcome, title=title, detail=render_reason(aop, code, **(data or {}))[0],
                   data=data or {}, stop=stop)


def _ok(title: str, check: str, stage: str, detail: str = "", data: dict | None = None) -> Finding:
    return Finding(check=check, stage=stage, status=Status.PASS, title=title, detail=detail, data=data or {})


def make_ctx(state, deps, aop) -> CheckContext:
    inv = invoice_of(state)
    m = state.get("match") or {}
    ctx = CheckContext(case_id=state["case_id"], invoice=inv, repo=deps.repo, ledger=deps.store.ledger,
                       history=deps.store.history, aop=aop, ai=deps.ai_for(state),
                       doc_type=state.get("doc_type"), txn_type=state.get("txn_type"),
                       vendor=deps.repo.vendor_by_gstin(inv.supplier_gstin),
                       po=deps.repo.po(m.get("po_number")) if m.get("po_number") else None,
                       pairs=[LinePair(**p) for p in m.get("pairs", [])])
    ctx.scratch.update({"pdf_info": state.get("pdf_info") or {}, "same_file_case": state.get("same_file_case"),
                        "text_blocks": [ParseBlock(**b) for b in state.get("text_blocks", [])],
                        "parse_blocks": [ParseBlock(**b) for b in state.get("parse_blocks", [])]})
    if m.get("contract_id"):
        ctx.scratch["contract"] = deps.repo.contract_for(ctx.vendor.vendor_id, m.get("po_number")) if ctx.vendor else None
    return ctx


def node(name: str, stage: str):
    """Announce the node, and turn any failure into a hold (fail closed)."""
    def wrap(fn):
        @wraps(fn)
        def run(state, deps):
            cid = state["case_id"]
            deps.bus.publish(cid, "node_started", {"node": name})
            try:
                update = fn(state, deps) or {}
            except GraphBubbleUp:
                raise  # LangGraph's own pause/resume signal, not a failure
            except AiUnavailable as e:
                aop = load_aop(deps.aop_path)
                f = _finding(aop, "AI_UNAVAILABLE", "An AI step could not run", name, stage, {"reason": str(e)}, stop=True)
                update = {"findings": _record(deps, state, [f]), "stopped": True}
            except Exception as e:  # a bug in a node must never let an invoice through
                aop = load_aop(deps.aop_path)
                f = _finding(aop, "TOOL_ERROR", f"Step '{name}' failed", name, stage,
                             {"check": name, "error": f"{type(e).__name__}: {e}"}, stop=True)
                update = {"findings": _record(deps, state, [f]), "stopped": True}
                if name == "decide":  # the decision itself failed: hold, with the error as the reason
                    update |= _hold_on_error(state, deps, aop, f)
            deps.bus.publish(cid, "node_finished", {"node": name})
            return update
        run.node_name = name
        return run
    return wrap


def _hold_on_error(state, deps, aop, f: Finding) -> dict:
    vd = {"outcome": int(Outcome.ON_HOLD), "primary_code": f.code, "why": f.detail,
          "owner": aop.reasons[f.code].owner, "next_step": render_reason(aop, f.code, **f.data)[1], "also": []}
    deps.store.set_outcome(state["case_id"], Outcome.ON_HOLD, f.code, vd["why"], vd["owner"], vd["next_step"], None,
                           state.get("txn_type"), state.get("doc_type"), [], aop.version)
    deps.bus.publish(state["case_id"], "decision", vd)
    return {"outcome": int(Outcome.ON_HOLD), "verdict": vd}

def _summarise(state, deps, inv: Invoice) -> None:
    v = deps.repo.vendor_by_gstin(inv.supplier_gstin)
    deps.store.set_invoice_summary(
        state["case_id"], vendor_id=v.vendor_id if v else None, vendor_name=v.name if v else inv.supplier_name,
        invoice_no=inv.invoice_no, invoice_no_norm=normal_invoice_no(inv.invoice_no), invoice_date=inv.invoice_date,
        grand_total=inv.grand_total, line_texts=[l.description for l in inv.lines], period_start=inv.period_start,
        invoice_json=json.dumps(_dump(inv)))


__all__ = [n for n in dir() if not n.startswith("__")]  # steps import everything here, helpers included

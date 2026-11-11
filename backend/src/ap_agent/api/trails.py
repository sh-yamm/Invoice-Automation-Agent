"""Purchase-order trails: each PO (or contract, or vendor billing without a PO) as one story in date order.

A trail holds the PO as it was sent, each goods receipt, every invoice the vendor sent against it, the agent's
decision on each, what people did, and a final "waiting for you" step when something is pending. Keys:
"PO-4518" (a PO, including a contract's blanket PO), "vendor-V007" (bills without a PO), "unmatched-C-1A2B3C"
(an invoice the agent could not place).
"""
from __future__ import annotations

import json
from decimal import Decimal

from ap_agent.api.trail import _po_number
from ap_agent.core.constants import BUYER_NAME, OUTCOME_LABELS
from ap_agent.core.money import fmt_inr, to_money

SHORT = "Sample Client"
NEEDS = (1, 2)  # needs sign-off, on hold
ORDER = {"contract": 0, "po": 1, "grn": 2, "invoice": 3, "check": 4, "decision": 5, "person": 6, "waiting": 9}
ACTIONS = {"approve_anyway": "Approved anyway", "sign_off": "Signed off", "reject": "Rejected",
           "ask_vendor": "Asked the vendor", "confirm_field": "Corrected a field", "recheck": "Re-checked"}


def _needs_person(c: dict) -> bool:
    return c.get("outcome") is not None and int(c["outcome"]) in NEEDS and c.get("status") != "done"


def case_key(case: dict, repo) -> str:
    po = _po_number(case, repo) or (case.get("assigned_po") if repo.po(case.get("assigned_po")) else None)
    if po and repo.po(po):
        return po
    if case.get("txn_type") == "po_less" and case.get("vendor_id"):
        return f"vendor-{case['vendor_id']}"
    return f"unmatched-{case['case_id']}"


def _cases_by_key(deps) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for summary in deps.store.list_cases({}):
        case = deps.store.get_case(summary["case_id"])
        out.setdefault(case_key(case, deps.repo), []).append(case)
    for cases in out.values():
        cases.sort(key=lambda c: c["created_at"])
    return out


def _invoice_events(case: dict, vendor_name: str) -> list[dict]:
    cid = case["case_id"]
    inv = json.loads(case["invoice_json"]) if case.get("invoice_json") else {}
    number = case.get("invoice_no") or inv.get("invoice_no") or case.get("filename") or cid
    total = case.get("grand_total")
    dated = f", dated {case['invoice_date']}" if case.get("invoice_date") else ""
    ev = [{"kind": "invoice", "date": case["created_at"], "actor": vendor_name, "case_id": cid,
           "title": f"Invoice {number} received",
           "detail": (f"{fmt_inr(Decimal(str(total)))} including GST" if total else "Being read") + dated,
           "doc": {"type": "invoice", "ref": cid}}]
    if case.get("outcome") is None:
        ev.append({"kind": "check", "date": case["created_at"], "actor": "Agent", "case_id": cid,
                   "title": "The agent is checking it now", "detail": "Each check appears as it runs.",
                   "doc": {"type": "invoice", "ref": cid}})
        return ev
    first = [h for h in case.get("human_actions", []) if h.get("action") in ACTIONS]
    agent_label = OUTCOME_LABELS[int(case["outcome"])]
    if first and case.get("primary_code") in ("APPROVED_BY_PERSON", "SIGNED_OFF", "REJECTED_BY_PERSON"):
        agent_label = "Needs a person"  # the agent's own call was a hold or sign-off; a person decided after
    ev.append({"kind": "decision", "date": case.get("decided_at") or case["created_at"], "actor": "Agent",
               "case_id": cid, "title": f"Agent: {agent_label}",
               "detail": case.get("why") or "", "doc": {"type": "invoice", "ref": cid}})
    for h in case.get("human_actions", []):
        ev.append({"kind": "person", "date": h.get("at"), "actor": h.get("actor") or "A person", "case_id": cid,
                   "title": ACTIONS.get(h.get("action"), (h.get("action") or "").replace("_", " ").capitalize()),
                   "detail": h.get("note") or "", "doc": {"type": "invoice", "ref": cid}})
    if _needs_person(case):
        ev.append({"kind": "waiting", "date": None, "actor": "You", "case_id": cid,
                   "title": f"Waiting for you: {case.get('owner') or 'review'}",
                   "detail": case.get("next_step") or "", "doc": {"type": "invoice", "ref": cid}})
    return ev


def _sort(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda e: (e["kind"] == "waiting", (e["date"] or "")[:19], ORDER[e["kind"]]))


def _money(deps, po) -> dict:
    billed = deps.store.ledger.invoiced(po.po_number)[1]
    return {"ordered": str(to_money(po.value)), "billed": str(to_money(billed)),
            "left": str(to_money(max(po.value - billed, Decimal("0"))))}


def trail_detail(key: str, deps, by_key: dict | None = None) -> dict | None:
    repo = deps.repo
    by_key = by_key if by_key is not None else _cases_by_key(deps)
    cases = by_key.get(key, [])
    if key.startswith("PO-") or repo.po(key):
        po = repo.po(key)
        if po is None:
            return None
        vendor = repo.vendor(po.vendor_id)
        vname = vendor.name if vendor else po.vendor_id
        contract = repo.contract_for(po.vendor_id, po.po_number)
        events = []
        if contract:
            events.append({"kind": "contract", "date": contract.start_date.isoformat(), "actor": SHORT, "case_id": None,
                           "title": f"Contract {contract.contract_id} signed",
                           "detail": f"{contract.description}: {fmt_inr(contract.amount_per_period)} per period, "
                                     f"{contract.start_date:%d %b %Y} to {contract.end_date:%d %b %Y}", "doc": None})
        lines = po.lines
        what = (f"{lines[0].qty:,.0f} {lines[0].unit} of {lines[0].description} at {fmt_inr(lines[0].rate)}"
                if len(lines) == 1 else f"{len(lines)} lines")
        events.append({"kind": "po", "date": po.po_date.isoformat(), "actor": SHORT, "case_id": None,
                       "title": f"PO {po.po_number} sent to {vname}",
                       "detail": f"{what}; {fmt_inr(po.value)} before GST", "doc": {"type": "po", "ref": po.po_number}})
        grns = {}
        for l in lines:
            for g in repo.grns(po.po_number, l.line_no):
                grns.setdefault(g.grn_number, []).append(g)
        for number, gs in grns.items():
            accepted = sum((g.accepted_qty for g in gs), Decimal("0"))
            unit = po.line(gs[0].line_no).unit if po.line(gs[0].line_no) and len(gs) == 1 else ""
            events.append({"kind": "grn", "date": max(g.received_date for g in gs).isoformat(), "actor": "Warehouse",
                           "case_id": None, "title": f"Goods received, {number}",
                           "detail": f"Accepted {accepted:,.0f} {unit}".strip() if unit else f"{len(gs)} lines accepted",
                           "doc": {"type": "grn", "ref": number}})
        for c in cases:
            events += _invoice_events(c, vname)
        kind = "contract" if contract else "po"
        title, money, po_type, status = po.po_number, _money(deps, po), po.po_type, po.status
        vendor_id = po.vendor_id
    elif key.startswith("vendor-"):
        vendor_id = key.split("-", 1)[1]
        vendor = repo.vendor(vendor_id)
        if vendor is None and not cases:
            return None
        vname = vendor.name if vendor else vendor_id
        events = [e for c in cases for e in _invoice_events(c, vname)]
        kind, title, money, po_type, status = "no_po", f"No PO · {vname}", None, None, "open"
    elif key.startswith("unmatched-"):
        if not cases:
            return None
        c = cases[0]
        vname = c.get("vendor_name") or "Unknown vendor"
        vendor_id, events = c.get("vendor_id"), _invoice_events(c, vname)
        kind, title, money, po_type, status = "unmatched", "Not matched to a PO", None, None, "open"
    else:
        return None
    events = _sort(events)
    waiting = next((c for c in cases if _needs_person(c)), None)
    shown = [e for e in events if e["date"]]
    latest = shown[-1] if shown else None
    return {"key": key, "kind": kind, "title": title, "vendor": vname, "vendor_id": vendor_id, "po_type": po_type,
            "po_status": status, "money": money, "events": events,
            "status": "needs_you" if waiting else ("closed" if status == "closed" else "open"),
            "needs_you": {"case_id": waiting["case_id"], "reason": waiting.get("why") or "",
                          "owner": waiting.get("owner"), "since": waiting["created_at"]} if waiting else None,
            "latest": {"date": latest["date"], "text": latest["title"]} if latest else None,
            "invoices": len(cases), "client": BUYER_NAME}


def list_trails(deps) -> list[dict]:
    by_key = _cases_by_key(deps)
    keys = [p.po_number for p in deps.repo.pos()] + [k for k in by_key if not k.startswith("PO-")]
    trails = [t for t in (trail_detail(k, deps, by_key) for k in dict.fromkeys(keys)) if t]
    for t in trails:
        t.pop("events", None)
    waiting = sorted((t for t in trails if t["needs_you"]), key=lambda t: t["needs_you"]["since"])
    rest = sorted((t for t in trails if not t["needs_you"]), key=lambda t: (t["latest"] or {}).get("date") or "",
                  reverse=True)
    return waiting + rest

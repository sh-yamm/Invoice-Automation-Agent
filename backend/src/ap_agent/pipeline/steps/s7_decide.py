"""Stage 7 · Decide: make sure every check ran, take the strictest rule outcome, let the AI review it
(stricter only), pause for a person on holds and sign-offs, then write the ledgers.

completeness_guard → decide → human_gate (pauses) → finalise
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


@node("completeness_guard", "decide")
def guard(state, deps):
    aop = load_aop(deps.aop_path)
    g = completeness_guard(state.get("txn_type"), findings_of(state), aop)
    f = g or _ok("Every required check for this path ran", "completeness_guard", "decide")
    return {"findings": _record(deps, state, [f])}


# ---------- 6. decision ----------

def _review_input(state, inv: Invoice, findings: list[Finding], floor_outcome: Outcome) -> str:
    return json.dumps({
        "rules_outcome": floor_outcome.name.lower(),
        "invoice": {"supplier": inv.supplier_name, "invoice_no": inv.invoice_no, "date": str(inv.invoice_date),
                    "total": str(inv.grand_total), "lines": [l.description for l in inv.lines],
                    "transaction_type": state.get("txn_type")},
        "findings": [{"id": f.id, "check": f.check, "status": f.status.value, "code": f.code, "title": f.title,
                      "detail": f.detail} for f in findings],
    }, ensure_ascii=False)


@node("decide", "decide")
def decide(state, deps):
    aop = load_aop(deps.aop_path)
    inv = invoice_of(state)
    findings = findings_of(state)
    outcome, primary = floor(findings, aop)
    new, note, reasoning = [], None, None
    if outcome is not Outcome.REJECTED and not state.get("stopped"):
        try:
            msgs = [{"role": "system", "content": REVIEW_SYSTEM},
                    {"role": "user", "content": _review_input(state, inv, findings, outcome)}]
            proposal, reasoning = deps.gateway.chat_json("agent", msgs, REVIEW_SCHEMA, case_id=state["case_id"],
                                                         node="agent_review", cache_key=_cache(state, "review"))
            note = proposal.get("rationale")
            final, accepted, warn = accept_escalation(outcome, proposal, findings, aop)
            if warn:
                new.append(warn)
            if accepted:
                esc = escalation_finding(final, proposal, aop)
                new.append(esc)
                outcome, primary = final, esc
        except (AiUnavailable, InvalidModelOutput) as e:
            if outcome is Outcome.APPROVED:  # fail closed: no approval without the review
                f = _finding(aop, "AI_UNAVAILABLE", "Agent review could not run", "agent_review", "decide",
                             {"reason": str(e)})
                new.append(f)
                outcome, primary = Outcome.ON_HOLD, f
            note = "The agent review could not run; the rule-based outcome stands."
    v = deps.repo.vendor_by_gstin(inv.supplier_gstin)
    all_findings = findings + new
    verdict = compose_verdict(outcome, primary, all_findings, aop, inv, v.payment_terms_days if v else 30)
    recorded = _record(deps, state, new)
    deps.store.set_outcome(state["case_id"], outcome, verdict.primary_code, verdict.why, verdict.owner,
                           verdict.next_step, note, state.get("txn_type"), state.get("doc_type"), verdict.also,
                           aop.version)
    vd = {"outcome": int(outcome), "primary_code": verdict.primary_code, "why": verdict.why, "owner": verdict.owner,
          "next_step": verdict.next_step, "also": verdict.also}
    deps.bus.publish(state["case_id"], "decision", vd | {"agent_note": note})
    return {"outcome": int(outcome), "verdict": vd, "agent_note": note, "agent_reasoning": reasoning,
            "findings": recorded}


# ---------- 7. human gate and finalise ----------

REVALIDATE_KEEP = {"ingest", "reconcile", "read", "classify"}
FAILURE_CODES = {"AI_UNAVAILABLE", "TOOL_ERROR", "EXTRACTION_FAILED"}


@node("human_gate", "human")
def human_gate(state, deps):
    action = interrupt({"case_id": state["case_id"], "outcome": state.get("outcome"),
                        "primary_code": (state.get("verdict") or {}).get("primary_code")})
    cid, kind = state["case_id"], action["action"]
    deps.bus.publish(cid, "human_action", {k: v for k, v in action.items() if k != "action_key"})
    aop = load_aop(deps.aop_path)
    failed = any(f.stop and f.code in FAILURE_CODES for f in findings_of(state))
    if kind == "recheck" and (failed or not state.get("invoice")):
        # the earlier run broke (model outage, crash, unreadable reply): start the whole case again
        deps.store.clear_findings(cid)
        deps.store.set_status(cid, "running")
        return {"action": action, "restart": True, "findings": [], "invoice": None, "parse_blocks": [],
                "text_blocks": [], "pages": [], "match": {}, "doc_type": None, "txn_type": None,
                "rerouted": False, "stopped": False, "outcome": None, "verdict": None}
    if kind in ("confirm_field", "recheck"):
        inv = invoice_of(state)
        if kind == "confirm_field":
            field, value = action["field"], action["value"]
            if field in ("invoice_date", "period_start", "period_end"):
                value = parse_date_in(value)
            elif field in ("taxable_total", "grand_total", "cgst", "sgst", "igst"):
                value = parse_inr(value)
            setattr(inv, field, value)
            inv.confidence[field] = 1.0
        if kind == "recheck":
            deps.reload()
        new_po = kind == "confirm_field" and action.get("field") == "po_ref"
        keep = REVALIDATE_KEEP - {"classify"} if new_po else REVALIDATE_KEEP  # a new PO: classify again
        kept = [f for f in findings_of(state) if f.stage in keep and f.check not in ("field_confidence", "po_assignment")]
        if new_po:
            deps.store.set_assigned_po(cid, inv.po_ref)
            kept.append(_ok(f"{inv.po_ref} assigned by {action.get('actor') or 'a person'}", "po_assignment", "read",
                            "A reviewer moved this invoice to this PO; it is checked against it again."))
        st = {**state, "invoice": _dump(inv)}
        kept += run_checks("read", make_ctx(st, deps, aop))
        if state.get("aop_version") and state["aop_version"] != aop.version:
            kept.append(_finding(aop, "AOP_VERSION_CHANGED", "Re-checked under a newer rulebook", "human_gate",
                                 "human", {"old": state["aop_version"], "new": aop.version}))
        deps.store.clear_findings(cid)
        for f in kept:
            deps.store.add_finding(cid, f)
        _summarise(state, deps, inv)
        deps.store.set_status(cid, "running")
        return {"invoice": _dump(inv), "findings": [f.model_dump(mode="json") for f in kept], "action": action,
                "aop_version": aop.version, "stopped": False,
                **({"assigned_po": inv.po_ref, "match": {}, "txn_type": None} if new_po else {})}
    if kind == "ask_vendor":
        deps.store.set_status(cid, "waiting_vendor")
        return {"action": action}
    inv = invoice_of(state)
    v = deps.repo.vendor_by_gstin(inv.supplier_gstin)
    actor, note = action.get("actor", "a person"), (action.get("note") or "").strip()
    if kind == "reject":
        outcome = Outcome.REJECTED
        why = f"Rejected by {actor} after review." + (f" Note: {note}" if note else "")
        nxt, owner = "Returned to the vendor with the reason.", "Vendor"
    else:
        outcome = Outcome.APPROVED
        pay = (inv.invoice_date + timedelta(days=v.payment_terms_days if v else 30)).strftime("%d %b %Y") \
            if inv.invoice_date else "the next payment run"
        label = "Signed off" if kind == "sign_off" else "Approved"
        primary = (state.get("verdict") or {}).get("primary_code")
        why = f"{label} by {actor} after review of {primary}." + (f" Note: {note}" if note else "")
        nxt, owner = f"Ready for payment on {pay}.", "No one"
    deps.store.set_outcome(cid, outcome, HUMAN_CODES[kind], why, owner, nxt, state.get("agent_note"),
                           state.get("txn_type"), state.get("doc_type"),
                           (state.get("verdict") or {}).get("also", []), aop.version)
    vd = {"outcome": int(outcome), "primary_code": HUMAN_CODES[kind], "why": why, "owner": owner, "next_step": nxt,
          "also": (state.get("verdict") or {}).get("also", [])}
    deps.bus.publish(cid, "decision", vd | {"agent_note": state.get("agent_note"), "by": actor})
    return {"outcome": int(outcome), "verdict": vd, "action": action}


@node("finalise", "finalise")
def finalise(state, deps):
    cid = state["case_id"]
    inv = invoice_of(state)
    m = state.get("match") or {}
    written = []
    if state.get("outcome") == int(Outcome.APPROVED):
        po = m.get("po_number")
        if state.get("txn_type") == "standard_po" and po:
            conv = m.get("conv", {})
            for p in m.get("pairs", []):
                line = inv.lines[p["inv_index"]]
                if p["po_line_no"] is None or p["method"] == "header":
                    deps.store.ledger_write(cid, po, 0, Decimal("0"), line.taxable)
                    written.append(f"{po} total +{fmt_inr(line.taxable)}")
                    continue
                qty = Decimal(conv[str(p["inv_index"])][0]) if str(p["inv_index"]) in conv else line.qty
                deps.store.ledger_write(cid, po, p["po_line_no"], qty, line.taxable)
                written.append(f"{po} line {p['po_line_no']} +{qty:g}")
        elif state.get("txn_type") == "recurring" and po:
            amount = inv.taxable_total or sum((l.taxable for l in inv.lines), Decimal("0"))
            deps.store.ledger_write(cid, po, 1, Decimal("0"), amount)
            written.append(f"{po} +{fmt_inr(amount)}")
            if m.get("contract_id") and inv.period_start:
                deps.store.period_write(cid, m["contract_id"], inv.period_start)
                written.append(f"{m['contract_id']} {inv.period_start:%B %Y} marked billed")
        deps.store.set_status(cid, "done")
    elif state.get("outcome") == int(Outcome.REJECTED):
        deps.store.set_status(cid, "done")
    deps.bus.publish(cid, "finalised", {"ledger": written, "outcome": state.get("outcome")})
    return {}

"""Stage 2 · Read: compare the PDF's hidden text with the page, extract the fields, keep only values seen on the page.

reconcile → extract → ground
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)
from ap_agent.reading.recover import recover_totals
from ap_agent.rules.po_assignment import apply_assigned_po


@node("reconcile", "reconcile")
def reconcile(state, deps):
    found = run_checks("reconcile", make_ctx(state, deps, load_aop(deps.aop_path)))
    return {"findings": _record(deps, state, found)}


@node("extract", "read")
def extract(state, deps):
    aop = load_aop(deps.aop_path)
    blocks = [ParseBlock(**b) for b in state.get("parse_blocks", [])]
    # Page images only for scans: a digital PDF's parsed text is complete, and images make the call much slower.
    images = [] if state.get("text_blocks") else state.get("pages", [])
    msgs = build_extract_messages(blocks, images)
    try:
        slot = "extract" if images else "extract_text"  # vision model only when it has to look at a scan
        raw, _ = deps.gateway.chat_json(slot, msgs, EXTRACT_SCHEMA, case_id=state["case_id"], node="extract",
                                        cache_key=_cache(state, "extract"))
    except InvalidModelOutput as e:
        f = _finding(aop, "EXTRACTION_FAILED", "The invoice could not be read into fields", "extract", "read",
                     {"reason": str(e)}, stop=True)
        return {"findings": _record(deps, state, [f]), "stopped": True}
    inv = to_invoice(raw)
    read = sum(1 for k in inv.confidence if k != "lines" and getattr(inv, k, None) not in (None, False))
    f = _ok(f"Read {read} fields and {len(inv.lines)} line(s)", "extract", "read",
            f"Lowest field confidence {min(inv.confidence.values(), default=1):.0%} "
            f"({deps.gateway.models.get(slot, slot) if hasattr(deps.gateway, 'models') else slot})")
    return {"invoice": _dump(inv), "findings": _record(deps, state, [f])}




@node("ground", "read")
def ground_node(state, deps):
    aop = load_aop(deps.aop_path)
    inv, found = ground(invoice_of(state), [ParseBlock(**b) for b in state.get("parse_blocks", [])])
    # A total or tax row the page reader dropped: take it from the PDF's own text, only if it adds up.
    inv, recovered = recover_totals(inv, [ParseBlock(**b) for b in state.get("text_blocks", [])])
    if recovered:
        names = {"grand_total": "invoice total", "igst": "IGST", "cgst": "CGST", "sgst": "SGST"}
        found.append(Finding(
            check="recover_totals", stage="read", status=Status.WARN,
            title="Read " + ", ".join(names[f] for f in recovered) + " from the PDF's own text",
            detail="The page reader missed " + ", ".join(f"the {names[f]} ({fmt_inr(getattr(inv, f))})" for f in recovered)
                   + ". The PDF's embedded text has exactly that figure, and it matches the taxable value plus tax"
                   + (" and the amount in words." if inv.amount_in_words else ".")))
    # The PO the person uploaded it to: used when none is printed, a hold when the invoice names another.
    inv, how = apply_assigned_po(inv, state.get("assigned_po"))
    if how == "assigned":
        found.append(_ok(f"{inv.po_ref} assigned by the person who uploaded it", "po_assignment", "read",
                         "No PO number is printed on the invoice, so it is checked against the PO it was uploaded to."))
    elif how == "mismatch":
        found.append(_finding(aop, "PO_ASSIGNMENT_MISMATCH", "Uploaded to a different PO", "po_assignment", "read",
                              {"assigned": state["assigned_po"], "printed": inv.po_ref}))
    st = {**state, "invoice": _dump(inv)}
    found += run_checks("read", make_ctx(st, deps, aop))
    _summarise(state, deps, inv)
    return {"invoice": _dump(inv), "findings": _record(deps, state, found)}

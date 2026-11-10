"""Stage 2 · Read: compare the PDF's hidden text with the page, extract the fields, keep only values seen on the page.

reconcile → extract → ground
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


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
    st = {**state, "invoice": _dump(inv)}
    found += run_checks("read", make_ctx(st, deps, aop))
    _summarise(state, deps, inv)
    return {"invoice": _dump(inv), "findings": _record(deps, state, found)}

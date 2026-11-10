"""Stage 3 · Classify: is it a payable tax invoice, and which path (standard PO, recurring, PO-less)?

classify_document → classify_transaction
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


@node("classify_document", "classify")
def classify_document_node(state, deps):
    aop = load_aop(deps.aop_path)
    inv = invoice_of(state)
    doc, conf, why = classify_document(inv, [ParseBlock(**b) for b in state.get("parse_blocks", [])], deps.gateway,
                                       case_id=state["case_id"], cache_key=_cache(state, "classify_document"))
    deps.store.set_classification(state["case_id"], doc, None, None, None)
    stopped = False
    if doc in NON_PAYABLE:
        f = _finding(aop, "NOT_A_TAX_INVOICE", f"Not a tax invoice: {DOC_LABELS.get(doc, doc)}", "classify_document",
                     "classify", {"doc_type": DOC_LABELS.get(doc, doc)}, stop=True)
        stopped = True
    elif doc in NOTES:
        f = _finding(aop, "CREDIT_NOTE_RECEIVED", f"This is a {DOC_LABELS[doc]}", "classify_document", "classify",
                     {"doc_type": DOC_LABELS[doc]}, stop=True)
        stopped = True
    else:
        f = _ok("Document is a tax invoice", "classify_document", "classify", why.capitalize())
    return {"doc_type": doc, "doc_confidence": conf, "doc_why": why, "stopped": stopped,
            "findings": _record(deps, state, [f])}


@node("classify_transaction", "classify")
def classify_transaction_node(state, deps):
    aop = load_aop(deps.aop_path)
    inv = invoice_of(state)
    txn, conf, why = classify_transaction(inv, deps.repo, deps.ai_for(state), deps.gateway, deps.store,
                                          state["case_id"], aop, cache_prefix=state.get("sample_id"))
    if txn not in TXN_LABELS or conf < aop.confidence.classification_min:
        f = _finding(aop, "CLASSIFICATION_UNCERTAIN", "Transaction type unclear", "classify_transaction", "classify",
                     {"why": why}, stop=True)
        deps.store.set_classification(state["case_id"], state.get("doc_type"), None, conf, why)
        return {"txn_type": None, "txn_confidence": conf, "txn_why": why, "stopped": True,
                "findings": _record(deps, state, [f])}
    deps.store.set_classification(state["case_id"], state.get("doc_type"), txn, conf, why)
    f = _ok(f"Classified as {TXN_LABELS[txn]} ({conf:.0%} sure)", "classify_transaction", "classify",
            why[:1].upper() + why[1:], {"txn_type": txn, "confidence": conf})
    return {"txn_type": txn, "txn_confidence": conf, "txn_why": why, "findings": _record(deps, state, [f])}

"""Stage 5 · Match: one of three paths, chosen by the transaction type.

standard_po (3-way: PO, receipt, invoice) | recurring (contract, period) | po_less (policy, GL coding)
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


def _match(state, deps, path: str) -> dict:
    ctx = make_ctx(state, deps, load_aop(deps.aop_path))
    ctx.txn_type = path
    found = run_checks("match", ctx, path=path)
    contract = ctx.scratch.get("contract")
    match = {"po_number": ctx.po.po_number if ctx.po else None,
             "pairs": [vars(p) for p in ctx.pairs], "contract_id": contract.contract_id if contract else None,
             "gl": ctx.scratch.get("gl"),
             "conv": {str(k): [str(q), str(r)] for k, (q, r) in ctx.scratch.get("conv", {}).items()}}
    update = {"match": match, "findings": _record(deps, state, found)}
    if ctx.scratch.get("reroute"):
        update.update(txn_type=ctx.scratch["reroute"], rerouted=True)
        deps.store.set_classification(state["case_id"], state.get("doc_type"), ctx.scratch["reroute"],
                                      state.get("txn_confidence"), "rerouted: an open PO matches the items")
    return update


@node("standard_po", "match")
def standard_po(state, deps):
    return _match(state, deps, "standard_po")


@node("recurring", "match")
def recurring(state, deps):
    return _match(state, deps, "recurring")


@node("po_less", "match")
def po_less(state, deps):
    return _match(state, deps, "po_less")

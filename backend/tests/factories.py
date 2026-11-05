"""Test builders. Sample invoices come from samples/specs.py, the same data the demo PDFs print."""
from __future__ import annotations

from samples.specs import SPECS


def make_invoice(sample: str = "S01", **overrides):
    inv = SPECS[sample].invoice.model_copy(deep=True)
    return inv.model_copy(update=overrides) if overrides else inv


# ---------- check contexts and fake AI ----------

class FakeAi:
    """Deterministic stand-in for the model-backed helpers."""

    def __init__(self, po_ranking=None, pair=None, gl=None):
        self.po_ranking = po_ranking or []          # list[(po_number, score, why)]
        self.pair = pair                            # (line_no|None, confidence, why) or None
        self.gl = gl or []                          # list[(gl_code, cost_centre, confidence, why)]
        self.calls: list[str] = []

    def rank_po_candidates(self, invoice, pos):
        self.calls.append("rank_po_candidates")
        return list(self.po_ranking)

    def pair_tiebreak(self, inv_line, candidates):
        self.calls.append("pair_tiebreak")
        return self.pair or (None, 0.0, "no match")

    def gl_code(self, invoice, accounts):
        self.calls.append("gl_code")
        return list(self.gl)

    def similarity(self, a: str, b: str) -> float:
        from rapidfuzz import fuzz
        return fuzz.token_set_ratio(a or "", b or "") / 100


_REPO = None


def repo():
    global _REPO
    if _REPO is None:
        from ap_agent.core.config import Settings
        from ap_agent.erp.repository import Repository
        _REPO = Repository.load(Settings().erp_dir)
    return _REPO


def make_ctx(invoice, store, *, ai=None, case_id="t-case", today=None, **kw):
    from ap_agent.checks.framework import CheckContext
    from ap_agent.core.config import Settings
    from ap_agent.rulebook.loader import load_aop

    r = repo()
    ctx = CheckContext(case_id=case_id, invoice=invoice, repo=r, ledger=store.ledger, history=store.history,
                       aop=load_aop(Settings().rulebook_path), ai=ai or FakeAi(),
                       vendor=r.vendor_by_gstin(invoice.supplier_gstin), **kw)
    if today is not None:
        ctx.today = today
    return ctx

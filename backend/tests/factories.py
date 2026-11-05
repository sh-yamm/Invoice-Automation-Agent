"""Test builders. Sample invoices come from samples/specs.py once Task 13 lands; S01 lives here until then."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from ap_agent.core.constants import BUYER_GSTIN, BUYER_NAME
from ap_agent.core.models import Invoice, Line

_S01 = dict(
    doc_title="TAX INVOICE",
    supplier_name="Shree Ganesh Office Furniture",
    supplier_gstin="29AAKFS4417M1ZM",
    supplier_phone="+91 80 4110 2290",
    supplier_email="accounts@shreeganeshfurniture.in",
    buyer_name=BUYER_NAME,
    buyer_gstin=BUYER_GSTIN,
    invoice_no="SGOF/26-27/0412",
    invoice_date=date(2026, 10, 29),
    po_ref="PO-4501",
    place_of_supply_state="29",
    bank_name="ICICI Bank",
    bank_account="000405112290",
    ifsc="ICIC0000004",
    lines=[
        Line(description="Ergonomic mesh chair", hsn_sac="9401", qty=D("20"), unit="Nos",
             rate=D("6450"), taxable=D("129000"), gst_rate=D("18")),
        Line(description="Workstation desk 1400mm", hsn_sac="9403", qty=D("10"), unit="Nos",
             rate=D("11200"), taxable=D("112000"), gst_rate=D("18")),
    ],
    taxable_total=D("241000"),
    cgst=D("21690"),
    sgst=D("21690"),
    igst=None,
    round_off=D("0"),
    grand_total=D("284380"),
    amount_in_words="Rupees Two Lakh Eighty Four Thousand Three Hundred Eighty Only",
)

_SAMPLES = {"S01": _S01}


def make_invoice(sample: str = "S01", **overrides) -> Invoice:
    base = dict(_SAMPLES[sample])
    base["lines"] = [l.model_copy() for l in base["lines"]]
    base.update(overrides)
    inv = Invoice(**base)
    if not inv.confidence:
        inv.confidence = {k: 0.98 for k in Invoice.model_fields if k not in ("confidence", "sources", "lines")}
    return inv


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

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

from datetime import date
from decimal import Decimal as D

import pytest

from ap_agent.checks.framework import run_checks
from ap_agent.core.models import Line, Status
from factories import FakeAi, make_ctx, make_invoice

TODAY = date(2026, 11, 6)
DECCAN = "36AAHFD3381L1Z6"
SAI = "33ABJFS2290H1Z4"


def run(inv, store, ai=None):
    ctx = make_ctx(inv, store, ai=ai, today=TODAY, txn_type="standard_po")
    return ctx, run_checks("match", ctx, path="standard_po")


def codes(findings, status=None):
    return {f.code for f in findings if f.code and (status is None or f.status is status)}


def steel(rate="61.80", qty="4000", unit="kg"):
    q, r = D(qty), D(rate)
    return make_invoice("S01", supplier_gstin=DECCAN, po_ref="PO-4518", cgst=None, sgst=None, taxable_total=q * r,
                        lines=[Line(description="MS angle 50x50x5 mm", hsn_sac="7216", qty=q, unit=unit,
                                    rate=r, taxable=q * r, gst_rate=D("18"))])


def test_s01_all_pass(store):
    ctx, f = run(make_invoice("S01"), store)
    assert codes(f, Status.FAIL) == set() and codes(f, Status.WARN) == set()
    assert ctx.po.po_number == "PO-4501" and [p.po_line_no for p in ctx.pairs] == [1, 2]
    assert {x.check for x in f} >= {"po_resolve", "po_vendor", "po_open", "line_pairing", "gst_rate", "units",
                                     "price", "qty_ordered", "grn_exists", "qty_received", "po_balance",
                                     "invoice_before_po"}


def test_price_variance_s02(store):
    _, f = run(steel(), store)
    pv = next(x for x in f if x.code == "PRICE_VARIANCE")
    assert pv.status is Status.FAIL and pv.data["variance_pct"] == 3.0
    assert "₹61.80" in pv.detail and "₹60.00" in pv.detail


def test_price_within_tolerance_passes_and_records_variance(store):
    _, f = run(steel(rate="60.60"), store)
    assert "PRICE_VARIANCE" not in codes(f)
    assert next(x for x in f if x.check == "price").data["variances"][0]["variance_pct"] == 1.0


def test_price_over_absolute_cap(store):
    _, f = run(steel(rate="61.10", qty="4000"), store)  # 1.83% but ₹4,400 extra … still within both
    assert "PRICE_VARIANCE" not in codes(f)
    _, f = run(steel(rate="61.10", qty="5000"), store)  # ₹5,500 extra > ₹5,000 cap, though only 1.83%
    assert "PRICE_VARIANCE" in codes(f)


def test_under_billed_is_warning(store):
    _, f = run(steel(rate="58.00"), store)
    assert "UNDER_BILLED" in codes(f, Status.WARN) and "PRICE_VARIANCE" not in codes(f)


def test_po_inferred(store):
    inv = make_invoice("S01", po_ref=None, lines=[Line(description="Filing cabinet, 4 drawer", hsn_sac="9403",
                       qty=D("8"), unit="Nos", rate=D("9800"), taxable=D("78400"), gst_rate=D("18"))])
    ctx, f = run(inv, store, ai=FakeAi(po_ranking=[("PO-4507", 0.94, "only open PO with filing cabinets"),
                                                   ("PO-4501", 0.20, "different items")]))
    assert "PO_INFERRED" in codes(f, Status.WARN) and ctx.po.po_number == "PO-4507"


def test_po_not_found_stops(store):
    ctx, f = run(make_invoice("S01", po_ref=None), store, ai=FakeAi(po_ranking=[("PO-4507", 0.60, "weak")]))
    nf = next(x for x in f if x.code == "PO_NOT_FOUND")
    assert nf.stop is True and ctx.po is None
    assert "price" not in {x.check for x in f}  # later checks skipped after a stop


def test_po_vendor_mismatch(store):
    _, f = run(make_invoice("S01", po_ref="PO-4518"), store)
    assert "PO_VENDOR_MISMATCH" in codes(f, Status.FAIL)


def test_unexpected_charges(store):
    inv = make_invoice("S01")
    inv.lines.append(Line(description="Freight charges", hsn_sac="996511", qty=D("1"), unit=None,
                          rate=D("3500"), taxable=D("3500"), gst_rate=D("18")))
    _, f = run(inv, store)
    uc = next(x for x in f if x.code == "UNEXPECTED_CHARGES")
    assert "Freight charges" in uc.detail


def test_gst_rate_mismatch(store):
    inv = make_invoice("S01")
    inv.lines[0] = inv.lines[0].model_copy(update={"gst_rate": D("12")})
    _, f = run(inv, store)
    assert "GST_RATE_MISMATCH" in codes(f, Status.FAIL)


def test_units_converted(store):
    _, f = run(steel(rate="60000", qty="4", unit="tonne"), store)
    assert codes(f, Status.FAIL) == set()
    price = next(x for x in f if x.check == "price")
    assert price.data["variances"][0]["variance_pct"] == 0.0


def test_units_not_convertible(store):
    _, f = run(steel(rate="60", qty="4000", unit="box"), store)
    assert "UNIT_MISMATCH" in codes(f, Status.FAIL)


def test_qty_exceeds_ordered(store):
    inv = make_invoice("S01")
    inv.lines[0] = inv.lines[0].model_copy(update={"qty": D("25"), "taxable": D("161250")})
    _, f = run(inv, store)
    assert "QTY_EXCEEDS_ORDERED" in codes(f, Status.FAIL)


def test_receipt_missing(store, monkeypatch):
    from factories import repo
    monkeypatch.setattr(repo(), "grns", lambda po, line: [])
    _, f = run(make_invoice("S01"), store)
    assert "RECEIPT_MISSING" in codes(f, Status.FAIL)


def test_services_po_is_two_way(store):
    inv = make_invoice("S01", supplier_gstin=SAI, po_ref="PO-4476", cgst=None, sgst=None,
                       lines=[Line(description="Freight Bengaluru to Chennai, 32 ft trailer", hsn_sac="996511",
                                   qty=D("2"), unit="Trips", rate=D("18500"), taxable=D("37000"), gst_rate=D("5"))])
    _, f = run(inv, store)
    grn = [x for x in f if x.check in ("grn_exists", "qty_received")]
    assert grn and all(x.status is Status.PASS and "2-way" in x.title for x in grn)


def test_already_invoiced_po(store):
    store.create_case("prev", "p.pdf", "p", None)
    store.ledger_write("prev", "PO-4501", 1, D("20"), D("129000"))
    store.ledger_write("prev", "PO-4501", 2, D("10"), D("112000"))
    _, f = run(make_invoice("S01"), store)
    assert {"QTY_EXCEEDS_RECEIVED", "PO_FULLY_INVOICED"} <= codes(f, Status.FAIL)


def test_po_balance_exceeded(store):
    store.create_case("prev", "p.pdf", "p", None)
    store.ledger_write("prev", "PO-4501", 1, D("0"), D("100000"))
    _, f = run(make_invoice("S01"), store)
    ob = next(x for x in f if x.code == "AMOUNT_EXCEEDS_PO_BALANCE")
    assert ob.data["over"] == "₹1,00,000.00"


def test_invoice_before_po(store):
    _, f = run(make_invoice("S01", invoice_date=date(2026, 10, 1)), store)
    assert "INVOICE_BEFORE_PO" in codes(f, Status.FAIL)


def test_header_level_for_lump_invoice(store):
    inv = make_invoice("S01", lines=[Line(description="Office furniture as per PO", hsn_sac="9403", qty=D("1"),
                                          unit=None, rate=D("241000"), taxable=D("241000"), gst_rate=D("18"))])
    ctx, f = run(inv, store)
    assert "HEADER_LEVEL_MATCH_ONLY" in codes(f, Status.WARN)
    assert codes(f, Status.FAIL) == set()


def test_agent_pairing_when_descriptions_differ(store):
    inv = make_invoice("S01")
    inv.lines[0] = inv.lines[0].model_copy(update={"description": "Revolving office seat, black"})
    ctx, f = run(inv, store, ai=FakeAi(pair=(1, 0.9, "same item, different wording")))
    assert "LLM_LINE_PAIRING" in codes(f, Status.WARN) and ctx.pairs[0].method == "agent"

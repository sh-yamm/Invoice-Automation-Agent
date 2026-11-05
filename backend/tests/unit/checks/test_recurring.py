from datetime import date
from decimal import Decimal as D

from ap_agent.checks.framework import run_checks
from ap_agent.core.models import Line, Status
from factories import make_ctx, make_invoice

TODAY = date(2026, 11, 6)
NIMBUS = "27AAPFN6620Q1ZH"


def nimbus(period_start=date(2026, 11, 1), amount="120000", invoice_no="NIT/26-27/091", invoice_date=date(2026, 11, 2)):
    a = D(amount)
    end = None if period_start is None else date(period_start.year + (period_start.month == 12),
                                                 period_start.month % 12 + 1, 1)
    return make_invoice("S01", supplier_gstin=NIMBUS, po_ref="PO-4490", invoice_no=invoice_no,
                        invoice_date=invoice_date, cgst=None, sgst=None, igst=a * D("0.18"),
                        taxable_total=a, grand_total=a * D("1.18"), amount_in_words=None,
                        period_start=period_start, period_end=end,
                        lines=[Line(description="IT support retainer", hsn_sac="998313", qty=D("1"),
                                    unit="Month", rate=a, taxable=a, gst_rate=D("18"))])


def run(inv, store, case_id="t-case"):
    ctx = make_ctx(inv, store, today=TODAY, txn_type="recurring", case_id=case_id)
    return ctx, run_checks("match", ctx, path="recurring")


def codes(findings, status=None):
    return {f.code for f in findings if f.code and (status is None or f.status is status)}


def test_s04_over_blanket_balance(store):
    ctx, f = run(nimbus(), store)
    over = next(x for x in f if x.code == "AMOUNT_EXCEEDS_PO_BALANCE")
    assert over.data["over"] == "₹60,000.00" and over.data["remaining"] == "₹60,000.00"
    assert ctx.scratch["contract"].contract_id == "CT-901"
    assert codes(f, Status.FAIL) == {"AMOUNT_EXCEEDS_PO_BALANCE"}
    assert {x.check for x in f} >= {"contract_resolve", "period_present", "contract_active", "period_not_billed",
                                     "advance_billing", "contract_amount", "contract_balance"}


def test_s05_period_already_billed(store):
    _, f = run(nimbus(period_start=date(2026, 10, 1), invoice_no="NIT/26-27/093"), store)
    pb = next(x for x in f if x.code == "PERIOD_ALREADY_BILLED")
    assert pb.data["other_no"] == "NIT/26-27/088" and "October 2026" in pb.detail
    assert "AMOUNT_EXCEEDS_PO_BALANCE" in codes(f)


def test_rerun_does_not_flag_own_period(store):
    store.create_case("own", "x.pdf", "h", None)
    store.period_write("own", "CT-901", date(2026, 11, 1))
    _, f = run(nimbus(), store, case_id="own")
    assert "PERIOD_ALREADY_BILLED" not in codes(f)
    assert next(x for x in f if x.check == "period_not_billed").status is Status.PASS


def test_contract_not_active(store):
    _, f = run(nimbus(period_start=date(2027, 4, 1), invoice_date=date(2026, 11, 2)), store)
    assert "CONTRACT_NOT_ACTIVE" in codes(f, Status.FAIL)


def test_contract_amount_mismatch(store):
    _, f = run(nimbus(amount="135000"), store)
    cm = next(x for x in f if x.code == "CONTRACT_AMOUNT_MISMATCH")
    assert cm.data["expected"] == "₹1,20,000.00" and cm.data["found"] == "₹1,35,000.00"


def test_period_missing(store):
    _, f = run(nimbus(period_start=None), store)
    assert "LOW_CONFIDENCE_FIELD" in codes(f, Status.FAIL)


def test_advance_billing_warns(store):
    _, f = run(nimbus(period_start=date(2026, 12, 1)), store)
    assert "ADVANCE_BILLING" in codes(f, Status.WARN)


def test_no_contract_stops(store):
    inv = nimbus().model_copy(update={"supplier_gstin": "29AAKFS4417M1ZM", "po_ref": None})
    _, f = run(inv, store)
    nc = next(x for x in f if x.code == "CONTRACT_NOT_FOUND")
    assert nc.stop is True

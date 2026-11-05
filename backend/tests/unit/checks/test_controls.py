from datetime import date
from decimal import Decimal as D

from ap_agent.checks.framework import run_checks
from ap_agent.core.models import Line, Outcome, Status
from factories import make_ctx, make_invoice

TODAY = date(2026, 11, 6)
KAVERI, LOOKALIKE, SAI, ORBIT = "29AADFK9013C1ZK", "29AADFK9813C1ZC", "33ABJFS2290H1Z4", "29AAJFO5521P1ZM"


def run(inv, store, case_id="t-case", txn_type="standard_po"):
    ctx = make_ctx(inv, store, today=TODAY, case_id=case_id, txn_type=txn_type)
    return ctx, run_checks("controls", ctx)


def codes(findings, status=None):
    return {f.code for f in findings if f.code and (status is None or f.status is status)}


def kaveri(**kw):
    base = dict(supplier_gstin=KAVERI, supplier_name="Kaveri Packaging Industries", po_ref="PO-4522",
                supplier_phone=None, supplier_email=None,
                invoice_no="KPI/26-27/1187", bank_name="ICICI Bank", bank_account="001205019023", ifsc="ICIC0000012",
                taxable_total=D("92500"), cgst=D("8325"), sgst=D("8325"), grand_total=D("109150"),
                lines=[Line(description="Corrugated box 5-ply 18x12x12", hsn_sac="4819", qty=D("5000"), unit="Nos",
                            rate=D("18.50"), taxable=D("92500"), gst_rate=D("18"))])
    base.update(kw)
    return make_invoice("S01", **base)


def freight(invoice_no, total="58275", trips="3", d=date(2026, 10, 26)):
    t = D(trips) * D("18500")
    return make_invoice("S01", supplier_gstin=SAI, supplier_name="Sai Krishna Logistics", supplier_phone=None,
                        supplier_email=None, invoice_no=invoice_no, invoice_date=d, po_ref="PO-4475",
                        bank_name=None, bank_account=None, ifsc=None, cgst=None, sgst=None, igst=t * D("0.05"),
                        taxable_total=t, grand_total=D(total),
                        lines=[Line(description="Freight Bengaluru to Chennai, 32 ft trailer", hsn_sac="996511",
                                    qty=D(trips), unit="Trips", rate=D("18500"), taxable=t, gst_rate=D("5"))])


def test_s01_all_pass(store):
    _, f = run(make_invoice("S01"), store)
    assert codes(f, Status.FAIL) == set() and codes(f, Status.WARN) == set()
    assert {x.check for x in f} >= {"vendor_approved", "lookalike_vendor", "vendor_identity", "bank_details",
                                     "duplicate_exact", "duplicate_fuzzy", "split_below_limit", "authority"}


def test_s03_bank_change(store):
    _, f = run(kaveri(bank_name="HDFC Bank", bank_account="50100231114471", ifsc="HDFC0000240"), store)
    b = next(x for x in f if x.code == "BANK_DETAILS_MISMATCH")
    assert b.outcome is Outcome.ON_HOLD and "4471" in b.detail and "9023" in b.detail


def test_bank_absent_is_pass(store):
    _, f = run(kaveri(bank_name=None, bank_account=None, ifsc=None), store)
    bank = next(x for x in f if x.check == "bank_details")
    assert bank.status is Status.PASS and "not printed" in bank.title.lower()


def test_masked_account_matching_last_digits_passes(store):
    _, f = run(kaveri(bank_account="XXXXXXXX9023", ifsc=None), store)
    assert "BANK_DETAILS_MISMATCH" not in codes(f)
    assert next(x for x in f if x.check == "bank_details").status is Status.PASS


def test_s15_lookalike(store):
    _, f = run(kaveri(supplier_gstin=LOOKALIKE, supplier_name="Kaveri Packaging Industry"), store)
    assert {"VENDOR_NOT_APPROVED", "LOOKALIKE_VENDOR"} <= codes(f, Status.FAIL)
    look = next(x for x in f if x.code == "LOOKALIKE_VENDOR")
    assert look.data["similar"] == "Kaveri Packaging Industries"


def test_renumbered_copy_normalises_to_exact_duplicate(store):
    _, f = run(freight("SKL/1043-A"), store)
    d = next(x for x in f if x.code == "DUPLICATE_EXACT")
    assert d.outcome is Outcome.REJECTED and d.data["other_case"] == "H-SKL-1043"


def test_s06_probable_duplicate(store):
    _, f = run(freight("SKL/1048"), store)
    d = next(x for x in f if x.code == "DUPLICATE_PROBABLE")
    assert d.status is Status.FAIL and d.data["other_case"] == "H-SKL-1043"
    assert "DUPLICATE_EXACT" not in codes(f)


def test_regular_vendor_different_amount_not_duplicate(store):
    # Same lines, close date and similar number, but a different amount: a normal next invoice (S16's shape).
    _, f = run(freight("SKL/1051", total="38850", trips="2", d=date(2026, 11, 4)), store)
    assert not codes(f) & {"DUPLICATE_PROBABLE", "DUPLICATE_EXACT"}
    assert {"duplicate_exact", "duplicate_fuzzy"} <= {x.check for x in f}


def test_same_number_different_amount(store):
    _, f = run(freight("SKL-1043", total="61000"), store)
    assert "DUPLICATE_NUMBER_DIFFERENT_AMOUNT" in codes(f, Status.FAIL)


def test_exact_duplicate_of_open_case_is_hold(store):
    store.create_case("open1", "a.pdf", "x", None)
    store.set_invoice_summary("open1", vendor_id="V002", vendor_name="Kaveri", invoice_no="KPI/26-27/1187",
                              invoice_no_norm="KPI26271187", invoice_date=date(2026, 10, 31),
                              grand_total=D("109150"), line_texts=["Corrugated box"], period_start=None)
    _, f = run(kaveri(), store)
    d = next(x for x in f if x.code == "DUPLICATE_EXACT")
    assert d.outcome is Outcome.ON_HOLD


def test_duplicate_search_excludes_own_case(store):
    store.create_case("me", "a.pdf", "x", None)
    store.set_invoice_summary("me", vendor_id="V002", vendor_name="Kaveri", invoice_no="KPI/26-27/1187",
                              invoice_no_norm="KPI26271187", invoice_date=date(2026, 10, 31),
                              grand_total=D("109150"), line_texts=["Corrugated box 5-ply 18x12x12"], period_start=None)
    _, f = run(kaveri(), store, case_id="me")
    assert not codes(f) & {"DUPLICATE_EXACT", "DUPLICATE_PROBABLE", "SPLIT_BELOW_LIMIT"}
    assert {"duplicate_exact", "duplicate_fuzzy", "split_below_limit"} <= {x.check for x in f}


def test_same_number_other_vendor_ok(store):
    _, f = run(make_invoice("S01", invoice_no="SKL-1043"), store)
    assert not codes(f) & {"DUPLICATE_EXACT", "DUPLICATE_PROBABLE", "DUPLICATE_NUMBER_DIFFERENT_AMOUNT"}
    assert "duplicate_exact" in {x.check for x in f}


def test_resubmission_of_rejected_warns(store):
    store.create_case("rej", "a.pdf", "x", None)
    store.set_invoice_summary("rej", vendor_id="V002", vendor_name="Kaveri", invoice_no="KPI/26-27/1180",
                              invoice_no_norm="KPI26271180", invoice_date=date(2026, 10, 30),
                              grand_total=D("109150"), line_texts=["Corrugated box 5-ply 18x12x12"], period_start=None)
    store.set_outcome("rej", Outcome.REJECTED, "MISSING_MANDATORY_FIELD", "x", "Vendor", "n", None, None, None)
    _, f = run(kaveri(), store)
    assert "RESUBMISSION_OF_REJECTED" in codes(f, Status.WARN)
    assert "DUPLICATE_PROBABLE" not in codes(f)


def test_s14_split_below_limit(store):
    inv = make_invoice("S01", supplier_gstin=ORBIT, supplier_name="Orbit Office Systems", supplier_phone=None,
                       supplier_email=None, invoice_no="ORB/26-27/0219", invoice_date=date(2026, 11, 4),
                       po_ref="PO-4540", bank_name=None, bank_account=None, ifsc=None,
                       taxable_total=D("415000"), cgst=D("37350"), sgst=D("37350"), grand_total=D("489700"),
                       lines=[Line(description="Workstation set, phase 3", hsn_sac="9403", qty=D("1"), unit="Set",
                                   rate=D("415000"), taxable=D("415000"), gst_rate=D("18"))])
    _, f = run(inv, store)
    s = next(x for x in f if x.code == "SPLIT_BELOW_LIMIT")
    assert s.outcome is Outcome.NEEDS_SIGNOFF and s.data["count"] == 3 and s.data["total"] == "₹14,69,100.00"
    assert "NEEDS_SIGNOFF" not in codes(f)


def test_authority_limit(store):
    _, f = run(make_invoice("S01", grand_total=D("742600")), store)
    assert "NEEDS_SIGNOFF" in codes(f, Status.FAIL)


def test_contact_details_changed_warns(store):
    _, f = run(make_invoice("S01", supplier_phone="+91 98450 00000"), store)
    assert "CONTACT_DETAILS_CHANGED" in codes(f, Status.WARN)

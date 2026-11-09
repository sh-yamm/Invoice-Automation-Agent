from datetime import date, timedelta
from decimal import Decimal

import pytest

from ap_agent.checks import framework
from ap_agent.checks.framework import check, run_checks
from ap_agent.core.constants import BUYER_GSTIN
from ap_agent.core.models import Line, Outcome, Status
from ap_agent.rules.india.words import amount_to_words
from factories import make_ctx, make_invoice

TODAY = date(2026, 11, 6)
MEHTA = "27AACCM4471B1ZR"
OTHER_VALID = "29AAGCR3310D1ZQ"


def _flip_last(g):
    return g[:-1] + ("A" if g[-1] != "A" else "B")


def _inter_state_v005(inv):
    """Turn S01 into a correctly taxed invoice from Mehta (Maharashtra → Karnataka, IGST)."""
    inv.supplier_gstin = MEHTA
    inv.cgst = inv.sgst = None
    inv.igst = Decimal("43380")
    inv.irn = "a" * 64
    return inv


MUTATIONS = {
    "none": (lambda i: i, None),
    "no_invoice_no": (lambda i: i.model_copy(update={"invoice_no": None}), "MISSING_MANDATORY_FIELD"),
    "bad_supplier_gstin": (lambda i: i.model_copy(update={"supplier_gstin": _flip_last(i.supplier_gstin)}), "INVALID_GSTIN"),
    "wrong_buyer": (lambda i: i.model_copy(update={"buyer_gstin": OTHER_VALID}), "WRONG_BUYER_GSTIN"),
    "einvoice_missing": (lambda i: _inter_state_v005(i).model_copy(update={"irn": None}), "EINVOICE_IRN_MISSING"),
    "einvoice_malformed": (lambda i: _inter_state_v005(i).model_copy(update={"irn": "abc"}), "INVALID_IRN"),
    "igst_on_intra_state": (lambda i: i.model_copy(update={"cgst": None, "sgst": None, "igst": Decimal("43380")}), "WRONG_TAX_TYPE"),
    "line_taxable_off": (lambda i: i.model_copy(update={"lines": [i.lines[0].model_copy(update={"taxable": Decimal("129100")}), i.lines[1]]}), "ARITHMETIC_MISMATCH"),
    "words_mismatch": (lambda i: i.model_copy(update={"amount_in_words": amount_to_words(Decimal("284830"))}), "AMOUNT_WORDS_MISMATCH"),
    "future_date": (lambda i: i.model_copy(update={"invoice_date": TODAY + timedelta(days=1)}), "FUTURE_DATED_INVOICE"),
}


@pytest.mark.parametrize("name", MUTATIONS)
def test_stage3(name, store):
    mutate, expected = MUTATIONS[name]
    inv = mutate(make_invoice("S01"))
    ctx = make_ctx(inv, store, today=TODAY)
    findings = run_checks("validate", ctx)
    failed = {f.code for f in findings if f.status is Status.FAIL}
    if expected is None:
        assert failed == set(), [(f.check, f.code, f.detail) for f in findings if f.status is Status.FAIL]
    else:
        assert expected in failed, [(f.check, f.code) for f in findings]
    assert {f.check for f in findings} >= {"rule46_fields", "supplier_gstin", "buyer_gstin", "tax_type",
                                           "arithmetic", "amount_in_words", "date_sanity", "einvoice_irn"}


def test_outcomes_come_from_rulebook(store):
    inv = make_invoice("S01", buyer_gstin=OTHER_VALID)
    f = next(f for f in run_checks("validate", make_ctx(inv, store, today=TODAY)) if f.code == "WRONG_BUYER_GSTIN")
    assert f.outcome is Outcome.REJECTED and OTHER_VALID in f.detail and "{" not in f.detail


def test_swapped_gstins_are_fixed_with_warning(store):
    inv = make_invoice("S01")
    inv = inv.model_copy(update={"supplier_gstin": inv.buyer_gstin, "buyer_gstin": inv.supplier_gstin})
    ctx = make_ctx(inv, store, today=TODAY)
    findings = run_checks("validate", ctx)
    assert not [f for f in findings if f.status is Status.FAIL]
    warn = next(f for f in findings if f.code == "GSTIN_SWAPPED_FIXED")
    assert warn.status is Status.WARN and "swapped" in warn.title.lower()
    assert ctx.invoice.buyer_gstin == BUYER_GSTIN and ctx.vendor.vendor_id == "V001"


def test_stale_date_is_warning_only(store):
    inv = make_invoice("S01", invoice_date=TODAY - timedelta(days=400))
    findings = run_checks("validate", make_ctx(inv, store, today=TODAY))
    stale = next(f for f in findings if f.code == "STALE_INVOICE_DATE")
    assert stale.status is Status.WARN and stale.outcome is None


def test_validate_handles_missing_optional_fields(store):
    inv = make_invoice("S01", bank_name=None, bank_account=None, ifsc=None, po_ref=None, amount_in_words=None,
                       lines=[Line(description="Consulting", hsn_sac=None, qty=Decimal("1"), unit=None,
                                   rate=Decimal("241000"), taxable=Decimal("241000"), gst_rate=Decimal("18"))])
    findings = run_checks("validate", make_ctx(inv, store, today=TODAY))
    assert not [f for f in findings if f.code == "TOOL_ERROR"]
    assert not [f for f in findings if f.status is Status.FAIL]


def test_unknown_vendor_does_not_crash_validation(store):
    inv = make_invoice("S01", supplier_gstin="29AADFK9813C1ZC")
    findings = run_checks("validate", make_ctx(inv, store, today=TODAY))
    assert not [f for f in findings if f.code == "TOOL_ERROR"]


def test_check_exception_becomes_tool_error(store, monkeypatch):
    monkeypatch.setattr(framework, "REGISTRY", dict(framework.REGISTRY))

    @check("boom", stage="validate", paths={"all"}, title="Explodes")
    def boom(ctx):
        raise RuntimeError("kaboom")

    findings = run_checks("validate", make_ctx(make_invoice("S01"), store, today=TODAY))
    err = next(f for f in findings if f.check == "boom")
    assert err.code == "TOOL_ERROR" and err.outcome is Outcome.ON_HOLD and "kaboom" in err.detail


def test_every_check_reports_something(store):
    findings = run_checks("validate", make_ctx(make_invoice("S01"), store, today=TODAY))
    ids = [s.id for s in framework.REGISTRY.values() if s.stage == "validate"]
    assert set(ids) <= {f.check for f in findings}


def test_required_checks_by_path():
    assert "rule46_fields" in framework.required_checks("standard_po")
    assert "rule46_fields" in framework.required_checks("po_less")


def test_irn_wrapped_across_two_lines_is_valid(store):
    """IRNs are 64 characters and usually wrap on the printed invoice; the reader returns them with a break."""
    inv = _inter_state_v005(make_invoice("S01"))
    inv.irn = "b2ac485dc4f9814b9592aa883689817f a117dd1c19fe6b4cd506f741fd8b9cb5"
    findings = run_checks("validate", make_ctx(inv, store, today=TODAY))
    assert "INVALID_IRN" not in {f.code for f in findings if f.status is Status.FAIL}

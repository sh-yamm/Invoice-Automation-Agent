"""Rates printed with GST included are converted to before-GST rates, but only when the numbers prove it."""
from decimal import Decimal as D

from ap_agent.core.models import Line
from ap_agent.rules.tax_inclusive import normalise_inclusive
from factories import make_invoice


def _inclusive(tax_shown: bool = True, taxable_total: str | None = "42000"):
    # 12 chairs at Rs 3,500 before GST = Rs 4,130 with 18% GST; lines printed with GST included.
    line = Line(description="Visitor chair, cantilever", hsn_sac="9401", qty=D("12"), unit="Nos", rate=D("4130"),
                taxable=D("49560"), gst_rate=D("18"))
    return make_invoice("S01", lines=[line], taxable_total=D(taxable_total) if taxable_total else None,
                        cgst=D("3780") if tax_shown else None, sgst=D("3780") if tax_shown else None, igst=None,
                        round_off=D("0"), grand_total=D("49560"))


def test_inclusive_rates_are_converted_to_before_gst():
    inv, info = normalise_inclusive(_inclusive())
    assert info is not None
    assert inv.lines[0].rate == D("3500.00") and inv.lines[0].taxable == D("42000.00")
    assert inv.taxable_total == D("42000") and inv.grand_total == D("49560")
    assert info["before_gst"] == "42000.00" and info["with_gst"] == "49560.00" and info["lines"] == 1


def test_a_missing_taxable_value_is_filled_from_the_converted_lines():
    inv, info = normalise_inclusive(_inclusive(taxable_total=None))
    assert info is not None and inv.taxable_total == D("42000.00")


def test_a_normal_invoice_is_left_alone():
    inv = make_invoice("S01")
    out, info = normalise_inclusive(inv)
    assert info is None and out.lines[0].rate == inv.lines[0].rate


def test_no_tax_shown_is_left_for_the_mandatory_field_check():
    """With no GST shown at all it isn't a valid tax invoice; converting would hide that."""
    inv, info = normalise_inclusive(_inclusive(tax_shown=False))
    assert info is None and inv.lines[0].rate == D("4130")


def test_a_line_without_a_gst_rate_is_not_guessed():
    inv = _inclusive()
    inv.lines[0].gst_rate = None
    out, info = normalise_inclusive(inv)
    assert info is None and out.lines[0].rate == D("4130")


def test_numbers_that_do_not_reconcile_are_not_converted():
    inv = _inclusive()
    inv.cgst = inv.sgst = D("1000")  # tax shown doesn't match the rates: not provably inclusive
    out, info = normalise_inclusive(inv)
    assert info is None and out.lines[0].rate == D("4130")


def test_a_rate_read_with_gst_and_an_amount_read_without_is_converted():
    """How the model actually read S17: the printed rate (with GST) but the taxable value (without)."""
    inv = _inclusive()
    inv.lines[0].taxable = D("42000")
    out, info = normalise_inclusive(inv)
    assert info is not None
    assert out.lines[0].rate == D("3500.00") and out.lines[0].taxable == D("42000")

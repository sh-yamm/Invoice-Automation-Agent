from datetime import date, datetime
from decimal import Decimal

import pytest

from ap_agent.rules.normalise import convert_qty, normal_invoice_no, parse_date_in, parse_inr, to_exclusive


@pytest.mark.parametrize("raw,expected", [
    ("1,29,000.00", "129000"), ("Rs. 58,275/-", "58275"), ("₹ 58,275", "58275"), ("INR 58275", "58275"),
    ("58275", "58275"), (58275, "58275"), (58275.5, "58275.5"), (Decimal("12.30"), "12.30"),
    ("₹ 2.84 L", "284000"), ("1.2 Cr", "12000000"), ("Rs.18,400.00", "18400"), ("(1,000.00)", "-1000"),
])
def test_parse_inr_variants(raw, expected):
    assert parse_inr(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "", None, "Rs.", "12-34", "1.2.3"])
def test_parse_inr_rejects_garbage(raw):
    assert parse_inr(raw) is None


def test_invoice_no_forms():
    assert normal_invoice_no("INV-001") == normal_invoice_no("INV001") == normal_invoice_no("1") == "1"
    assert normal_invoice_no("SKL/1043-A") == normal_invoice_no("SKL-1043") == "SKL1043"
    assert normal_invoice_no("sgof/26-27/0412") == normal_invoice_no("SGOF 26-27 412")
    assert normal_invoice_no("SKL/1048") != normal_invoice_no("SKL-1043")
    assert normal_invoice_no(None) == ""


@pytest.mark.parametrize("raw,expected", [
    ("02/11/2026", date(2026, 11, 2)), ("02-11-26", date(2026, 11, 2)), ("2 Nov 2026", date(2026, 11, 2)),
    ("2nd November 2026", date(2026, 11, 2)), ("29.10.2026", date(2026, 10, 29)), ("2026-10-29", date(2026, 10, 29)),
    (date(2026, 1, 5), date(2026, 1, 5)), (datetime(2026, 1, 5, 10, 0), date(2026, 1, 5)),
])
def test_date_indian(raw, expected):
    assert parse_date_in(raw) == expected


def test_date_never_month_first():
    assert parse_date_in("11/02/2026") == date(2026, 2, 11)
    assert parse_date_in("13/31/2026") is None
    assert parse_date_in("soon") is None and parse_date_in(None) is None


def test_units():
    assert convert_qty(Decimal("4"), "tonne", "kg") == Decimal("4000")
    assert convert_qty(Decimal("4000"), "KGS", "MT") == Decimal("4")
    assert convert_qty(Decimal("2"), "dozen", "Nos") == Decimal("24")
    assert convert_qty(Decimal("20"), "pcs", "Nos") == Decimal("20")
    assert convert_qty(Decimal("3"), "Trips", "trip") == Decimal("3")
    assert convert_qty(Decimal("5"), "box", "piece") is None
    assert convert_qty(Decimal("5"), None, "Nos") == Decimal("5")


def test_to_exclusive():
    assert to_exclusive(Decimal("118"), Decimal("18")) == Decimal("100.00")
    assert to_exclusive(Decimal("105"), Decimal("5")) == Decimal("100.00")

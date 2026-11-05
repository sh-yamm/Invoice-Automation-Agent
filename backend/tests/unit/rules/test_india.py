import csv
from decimal import Decimal

import pytest

from ap_agent.core.config import Settings
from ap_agent.core.constants import BUYER_GSTIN
from ap_agent.rules.india.gstin import gstin_check_digit, gstin_state, is_valid_gstin
from ap_agent.rules.india.words import amount_to_words, words_to_amount

BASES = ["29AABCZ5821K1Z", "27AAPFN6620Q1Z", "36AAHFD3381L1Z", "33ABJFS2290H1Z", "07AAACR5055K1Z"]


@pytest.mark.parametrize("base", BASES)
def test_check_digit_roundtrip(base):
    assert is_valid_gstin(base + gstin_check_digit(base))


def test_known_public_example():
    # A GSTIN widely used as a format example; confirms the algorithm matches the standard.
    assert gstin_check_digit("27AAPFU0939F1Z") == "V"


def test_tampered_digit_invalid():
    g = BASES[0] + gstin_check_digit(BASES[0])
    tampered = g[:7] + ("1" if g[7] != "1" else "2") + g[8:]
    assert not is_valid_gstin(tampered)
    assert not is_valid_gstin(g[:-1] + ("A" if g[-1] != "A" else "B"))


def test_malformed_gstins_invalid():
    for g in ["", None, "29AABCZ5821K1Z", "29aabcz5821k1zw", "2AABCZ5821K1ZWX", "29AABCZ5821K0ZW"]:
        assert not is_valid_gstin(g)


def test_buyer_gstin_valid():
    assert is_valid_gstin(BUYER_GSTIN)


def test_every_vendor_gstin_in_master_is_valid():
    with open(Settings().erp_dir / "vendors.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            assert is_valid_gstin(row["gstin"]), row["vendor_id"]
            assert gstin_state(row["gstin"]) == row["state_code"]


@pytest.mark.parametrize("amount", ["58275", "129000", "12900000.50", "501", "38850", "100000", "1", "0.75"])
def test_words_roundtrip(amount):
    assert words_to_amount(amount_to_words(Decimal(amount))) == Decimal(amount)


def test_words_lakh_crore():
    assert "One Crore Twenty Nine Lakh" in amount_to_words(Decimal("12900000"))
    assert amount_to_words(Decimal("284380")) == "Rupees Two Lakh Eighty Four Thousand Three Hundred Eighty Only"
    assert amount_to_words(Decimal("501.50")) == "Rupees Five Hundred One and Fifty Paise Only"


def test_words_tolerant_parsing():
    assert words_to_amount("Rs. Fifty-Eight Thousand Two Hundred and Seventy-Five Only") == Decimal("58275")
    assert words_to_amount("INR TWO LAKH EIGHTY FOUR THOUSAND THREE HUNDRED EIGHTY ONLY") == Decimal("284380")
    assert words_to_amount("not a number at all") is None
    assert words_to_amount(None) is None


def test_words_mismatch_detectable():
    assert words_to_amount("Fifty Eight Thousand Seven Hundred Twenty Five") != Decimal("58275")
    assert words_to_amount("Thirty Eight Thousand Five Hundred Eighty") == Decimal("38580")

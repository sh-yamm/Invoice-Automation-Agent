from decimal import Decimal

import pdfplumber
import pytest

from ap_agent.core.models import Outcome
from ap_agent.rules.india.gstin import is_valid_gstin
from ap_agent.rules.india.words import words_to_amount
from samples.generate import generate
from samples.specs import SPECS


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    out = tmp_path_factory.mktemp("pdf")
    return {sid: generate(spec, out) for sid, spec in SPECS.items()}


def text_of(path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_sixteen_specs_with_expectations():
    assert sorted(SPECS) == [f"S{i:02d}" for i in range(1, 17)]
    for s in SPECS.values():
        assert isinstance(s.expected_outcome, Outcome) and s.expected_code and s.title and s.blurb


def test_all_specs_generate(pdfs):
    for sid, path in pdfs.items():
        assert path.exists() and path.stat().st_size > 1000, sid
        with pdfplumber.open(path) as pdf:
            assert len(pdf.pages) == 1


def test_printed_text_matches_spec(pdfs):
    t = text_of(pdfs["S01"])
    assert "SGOF/26-27/0412" in t and "PO-4501" in t and "29AAKFS4417M1ZM" in t and "2,84,380.00" in t
    assert "TAX INVOICE" in t.upper()
    assert "PROFORMA" in text_of(pdfs["S11"]).upper()
    assert "pre-approved" in text_of(pdfs["S12"])


def test_s08_has_no_text_layer(pdfs):
    assert text_of(pdfs["S08"]).strip() == ""


def test_s13_text_layer_differs(pdfs):
    t = text_of(pdfs["S13"])
    assert "29,169.60" in t and "2,91,696.00" in t


def test_specs_internally_consistent():
    for sid, s in SPECS.items():
        inv = s.invoice
        assert sum(l.taxable for l in inv.lines) == inv.taxable_total, sid
        for l in inv.lines:
            assert l.qty * l.rate == l.taxable, sid
        tax = sum(x for x in (inv.cgst, inv.sgst, inv.igst) if x)
        assert inv.taxable_total + tax + (inv.round_off or 0) == inv.grand_total, sid
        assert is_valid_gstin(inv.supplier_gstin), sid
        words = words_to_amount(inv.amount_in_words)
        if sid == "S16":
            assert words == Decimal("38580") and inv.grand_total == Decimal("38850")
        else:
            assert words == inv.grand_total, sid


def test_s08_date_is_low_confidence_in_spec():
    assert SPECS["S08"].invoice.confidence["invoice_date"] < 0.85 and SPECS["S08"].invoice.po_ref is None

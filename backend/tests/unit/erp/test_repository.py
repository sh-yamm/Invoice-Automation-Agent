from datetime import date
from decimal import Decimal

import pytest

from ap_agent.erp.repository import Repository
from factories import make_invoice


@pytest.fixture(scope="module")
def repo():
    from ap_agent.core.config import Settings

    return Repository.load(Settings().erp_dir)


def test_vendor_by_gstin(repo):
    v = repo.vendor_by_gstin("29AAKFS4417M1ZM")
    assert v.vendor_id == "V001" and v.name == "Shree Ganesh Office Furniture"
    assert v.bank_account.endswith("2290") and v.einvoice_required is False


def test_einvoice_flag_and_category(repo):
    assert repo.vendor("V005").einvoice_required is True
    assert repo.vendor("V007").category == "utilities"


def test_po_value(repo):
    assert repo.po("PO-4490").value == Decimal("660000")
    assert repo.po("PO-4501").value == Decimal("241000")
    assert repo.po("PO-4540").value == Decimal("1245000")


def test_po_lines_grouped(repo):
    po = repo.po("PO-4501")
    assert po.vendor_id == "V001" and po.po_type == "goods" and [l.line_no for l in po.lines] == [1, 2]
    assert po.lines[0].hsn_sac == "9401" and po.lines[0].rate == Decimal("6450")


def test_open_pos_for_vendor(repo):
    assert {p.po_number for p in repo.open_pos("V001")} == {"PO-4501", "PO-4507"}


def test_grns(repo):
    g = repo.grns("PO-4501", 1)
    assert sum(x.accepted_qty for x in g) == Decimal("20")
    assert repo.grns("PO-4475", 1) == []


def test_contract_for_nimbus(repo):
    c = repo.contract_for("V003", "PO-4490")
    assert c.contract_id == "CT-901" and c.amount_per_period == Decimal("120000")
    assert c.start_date == date(2026, 6, 1) and c.end_date == date(2027, 3, 31)
    assert repo.contract_for("V003", None).contract_id == "CT-901"
    assert repo.contract_for("V001", None) is None


def test_lookalike_not_in_master(repo):
    assert repo.vendor_by_gstin("29AADFK9813C1ZC") is None
    assert all(v.name != "Kaveri Packaging Industry" for v in repo.vendors())


def test_gl_and_service_accounts(repo):
    codes = {a.gl_code for a in repo.gl_accounts()}
    assert {"6110", "6120", "6130", "6210"} <= codes and len(codes) >= 8
    assert repo.service_account("V007", "KA-BLR-0048213").cost_centre
    assert repo.service_account("V007", "KA-BLR-0000000") is None


def test_factory_s01_is_clean_and_overridable():
    inv = make_invoice("S01")
    assert inv.po_ref == "PO-4501" and inv.grand_total == Decimal("284380")
    assert sum(l.taxable for l in inv.lines) == inv.taxable_total
    assert make_invoice("S01", po_ref=None).po_ref is None

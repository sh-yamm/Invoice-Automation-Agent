"""People's changes to the company records: vendors (add, bank, block) and purchase orders. Each is logged."""
import shutil
from datetime import date
from decimal import Decimal

import pytest

from ap_agent.core.config import Settings
from ap_agent.erp.records import RecordError, add_vendor, change_bank, raise_po, set_vendor_status
from ap_agent.erp.repository import Repository

NEW = dict(name="Pune Paper Mills", gstin="27AAACP1234Q1Z5", address="Pune", phone="+91 20 1111 2222",
           email="ar@punepaper.in", bank_name="HDFC Bank", bank_account="50100011112222", ifsc="HDFC0000123",
           einvoice_required=False, payment_terms_days=30, category="packaging", actor="AP lead", why="new supplier")


@pytest.fixture
def erp(tmp_path):
    d = tmp_path / "erp"
    shutil.copytree(Settings().erp_dir, d)
    return d


def _valid_gstin():
    from ap_agent.rules.india.gstin import gstin_check_digit
    base = "27AAACP1234Q1Z"
    return base + gstin_check_digit(base)


def test_add_vendor_checks_the_gstin(erp, store):
    with pytest.raises(RecordError, match="GSTIN"):
        add_vendor(erp, store, **{**NEW, "gstin": "27AAACP1234Q1Z0"})


def test_add_vendor_then_it_is_approved_for_the_next_invoice(erp, store):
    vid = add_vendor(erp, store, **{**NEW, "gstin": _valid_gstin()})
    v = Repository.load(erp).vendor(vid)
    assert v.status == "active" and v.state_code == "27" and v.name == "Pune Paper Mills"
    assert store.record_changes(vid)[0]["kind"] == "vendor_added"
    with pytest.raises(RecordError, match="already"):
        add_vendor(erp, store, **{**NEW, "gstin": _valid_gstin()})


def test_bank_change_is_logged_with_who_and_why(erp, store):
    change_bank(erp, store, "V002", bank_name="HDFC Bank", bank_account="50100231114471", ifsc="HDFC0000240",
                actor="AP lead", why="Signed letter from the vendor, confirmed by phone")
    assert Repository.load(erp).vendor("V002").bank_account == "50100231114471"
    log = store.record_changes("V002")[0]
    assert log["kind"] == "bank_changed" and log["actor"] == "AP lead" and "letter" in log["why"]
    with pytest.raises(RecordError, match="why"):
        change_bank(erp, store, "V002", bank_name="X", bank_account="1", ifsc="X", actor="AP lead", why=" ")


def test_blocked_vendor_cannot_get_a_po(erp, store):
    set_vendor_status(erp, store, "V001", "blocked", actor="AP lead", why="GST registration cancelled")
    assert Repository.load(erp).vendor("V001").status == "blocked"
    with pytest.raises(RecordError, match="blocked"):
        raise_po(erp, store, vendor_id="V001", po_type="goods", po_date=date(2026, 11, 11),
                 lines=[{"description": "Chair", "hsn_sac": "9401", "qty": "5", "unit": "Nos", "rate": "4000",
                         "gst_rate": "18"}], actor="Buyer", why="office")


def test_raise_po_numbers_after_the_highest(erp, store):
    highest = max(int(p.po_number.split("-")[1]) for p in Repository.load(erp).pos())
    po = raise_po(erp, store, vendor_id="V004", po_type="goods", po_date=date(2026, 11, 11), actor="Buyer",
                  why="steel for the new store", lines=[
                      {"description": "MS angle 50x50x5 mm", "hsn_sac": "7216", "qty": "1000", "unit": "kg", "rate": "60", "gst_rate": "18"},
                      {"description": "MS flat bar 40x6 mm", "hsn_sac": "7216", "qty": "500", "unit": "kg", "rate": "62.5", "gst_rate": "18"}])
    assert po == f"PO-{highest + 1}"
    got = Repository.load(erp).po(po)
    assert got.status == "open" and got.value == Decimal("91250") and len(got.lines) == 2
    assert store.record_changes(po)[0]["kind"] == "po_raised"
    with pytest.raises(RecordError, match="line"):
        raise_po(erp, store, vendor_id="V004", po_type="goods", po_date=date(2026, 11, 11), lines=[], actor="B", why="x")

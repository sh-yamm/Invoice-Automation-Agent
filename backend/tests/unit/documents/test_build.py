"""The PO as it was sent to the vendor, and the goods receipt, as documents for the trail viewer."""
from ap_agent.core.config import Settings
from ap_agent.documents.build import grn_document, po_document
from ap_agent.erp.repository import Repository
from ap_agent.reading.text_layer import text_layer


def _text(png):
    return " ".join(b.text for b in text_layer(png.with_suffix(".pdf")))


def test_po_document_prints_the_order(tmp_path):
    repo = Repository.load(Settings().erp_dir)
    po = repo.po("PO-4501")
    png = po_document(po, repo.vendor(po.vendor_id), tmp_path)
    assert png.exists() and png.suffix == ".png"
    t = _text(png)
    for s in ("PURCHASE ORDER", "PO-4501", "Shree Ganesh Office Furniture", "Sample Client Retail",
              "Ergonomic mesh chair", "Workstation desk 1400mm", "2,41,000.00"):
        assert s in t, s
    assert po_document(po, repo.vendor(po.vendor_id), tmp_path) == png  # cached


def test_grn_document_lists_accepted_quantities(tmp_path):
    repo = Repository.load(Settings().erp_dir)
    po = repo.po("PO-4518")
    grns = [g for g in repo.all_grns() if g.grn_number == "GRN-7741"]
    t = _text(grn_document(grns, po, repo.vendor(po.vendor_id), tmp_path))
    for s in ("GOODS RECEIPT NOTE", "GRN-7741", "PO-4518", "MS angle 50x50x5 mm", "4,000"):
        assert s in t, s

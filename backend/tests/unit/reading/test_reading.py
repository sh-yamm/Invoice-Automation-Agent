import hashlib
from datetime import date
from pathlib import Path

import pytest

from ap_agent.checks.framework import run_checks
from ap_agent.core.config import REPO_ROOT
from ap_agent.core.models import Invoice, Outcome, Status
from ap_agent.reading.parse import parse_blocks
from ap_agent.reading.pdfinfo import inspect_pdf
from ap_agent.reading.render import render_pages
from ap_agent.reading.text_layer import text_layer
from ap_agent.reading.ground import ground
from factories import make_ctx, make_invoice

PDF = REPO_ROOT / "samples" / "pdf"
FIX = Path(__file__).resolve().parents[2] / "fixtures" / "parse"


def blocks(sample):
    return parse_blocks((FIX / f"{sample}.p1.txt").read_text(encoding="utf-8"), page=1)


def intake_ctx(store, sample, inv=None, **scratch):
    pdf = PDF / f"{sample}.pdf"
    ctx = make_ctx(inv or Invoice(), store, case_id=f"case-{sample}")
    info = inspect_pdf(pdf)
    ctx.scratch.update({"pdf_info": info, "text_blocks": text_layer(pdf) if not info["error"] else [],
                        "parse_blocks": blocks(sample) if (FIX / f"{sample}.p1.txt").exists() else []})
    ctx.scratch.update(scratch)
    return ctx


def test_parse_blocks_from_fixture():
    b = blocks("S01")
    sgof = [x for x in b if "SGOF" in x.text]
    assert sgof and all(0 <= v <= 1 for v in sgof[0].box) and sgof[0].page == 1
    assert sgof[0].box[0] < sgof[0].box[2] and sgof[0].box[1] < sgof[0].box[3]
    table = next(x for x in b if x.cls == "Table" and "Ergonomic" in x.text)
    assert "1,29,000.00" in table.text and "\\" not in table.text and "**" not in table.text
    assert any(x.cls == "Title" and "TAX INVOICE" in x.text for x in b)


def test_parse_blocks_tolerates_missing_end_tag():
    b = parse_blocks("<x_0.1><y_0.1>first block\n<x_0.2><y_0.3>second<x_0.5><y_0.4><class_Text>", page=2)
    assert [x.text for x in b] == ["first block", "second"] and b[1].box == (0.2, 0.3, 0.5, 0.4)


def test_render_page_count(tmp_path):
    pages = render_pages(PDF / "S01.pdf", tmp_path)
    assert len(pages) == 1 and pages[0].exists() and pages[0].suffix == ".png"


def test_inspect_pdf_basics():
    info = inspect_pdf(PDF / "S01.pdf")
    assert info["pages"] == 1 and info["error"] is None and info["encrypted"] is False
    assert info["sha256"] == hashlib.sha256((PDF / "S01.pdf").read_bytes()).hexdigest()
    assert inspect_pdf(Path(__file__))["error"]  # a .py file is not a PDF


def test_scanned_has_no_text_layer():
    assert text_layer(PDF / "S08.pdf") == []
    assert text_layer(PDF / "S01.pdf")


def test_ground_keeps_values_on_the_page():
    inv, findings = ground(make_invoice("S01"), blocks("S01"))
    assert inv.po_ref == "PO-4501" and inv.invoice_no == "SGOF/26-27/0412"
    assert inv.sources["grand_total"].box and inv.sources["supplier_gstin"].page == 1
    assert not [f for f in findings if f.status is not Status.PASS]


def test_ground_drops_hallucinated_po():
    inv, findings = ground(make_invoice("S01", po_ref="PO-9999"), blocks("S01"))
    assert inv.po_ref is None and inv.confidence["po_ref"] == 0
    w = next(f for f in findings if f.code == "UNGROUNDED_VALUE")
    assert w.status is Status.WARN and "PO-9999" in w.detail


def test_ground_drops_hallucinated_amount():
    inv, _ = ground(make_invoice("S01", grand_total=make_invoice("S01").grand_total + 450), blocks("S01"))
    assert inv.grand_total is None


def test_s01_reconcile_is_clean(store):
    f = run_checks("reconcile", intake_ctx(store, "S01"))
    assert {x.status for x in f} == {Status.PASS}
    assert {x.check for x in f} == {"text_layer_match", "tamper_signals", "injection_scan"}


def test_text_layer_mismatch_s13(store):
    f = run_checks("reconcile", intake_ctx(store, "S13"))
    m = next(x for x in f if x.code == "TEXT_LAYER_MISMATCH")
    assert m.outcome is Outcome.ON_HOLD and "29,169.60" in m.detail


def test_injection_s12(store):
    ctx = intake_ctx(store, "S12")
    f = run_checks("reconcile", ctx)
    inj = next(x for x in f if x.code == "SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT")
    assert inj.outcome is Outcome.ON_HOLD and "pre-approved" in inj.detail


def test_same_file_twice_stop(store):
    ctx = intake_ctx(store, "S01", same_file_case={"case_id": "c-old", "invoice_no": "SGOF/26-27/0412",
                                                   "outcome": "approved"})
    f = run_checks("ingest", ctx)
    d = next(x for x in f if x.code == "DUPLICATE_EXACT")
    assert d.stop is True and d.outcome is Outcome.REJECTED and d.data["other_case"] == "c-old"


def test_unreadable_file_stops(store):
    ctx = intake_ctx(store, "S01")
    ctx.scratch["pdf_info"] = inspect_pdf(Path(__file__))
    f = run_checks("ingest", ctx)
    assert [x.code for x in f if x.stop] == ["UNREADABLE_DOCUMENT"]


def test_tamper_signals_warn(store):
    ctx = intake_ctx(store, "S01")
    ctx.scratch["pdf_info"] = ctx.scratch["pdf_info"] | {"producer": "iLovePDF", "created": "2026-10-29",
                                                         "modified": "2026-11-05"}
    f = run_checks("reconcile", ctx)
    assert next(x for x in f if x.code == "DOCUMENT_TAMPER_SIGNALS").status is Status.WARN


def test_field_confidence_s08(store):
    ctx = make_ctx(make_invoice("S08"), store)
    f = run_checks("read", ctx)
    low = next(x for x in f if x.code == "LOW_CONFIDENCE_FIELD")
    assert "invoice date" in low.detail and "71%" in low.detail and low.evidence[0].field == "invoice_date"


def test_field_confidence_clean(store):
    f = run_checks("read", make_ctx(make_invoice("S01"), store))
    assert {x.status for x in f} == {Status.PASS}

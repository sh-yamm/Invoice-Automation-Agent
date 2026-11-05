from datetime import date
from decimal import Decimal as D

from ap_agent.checks.framework import run_checks
from ap_agent.core.models import Line, Status
from factories import FakeAi, make_ctx, make_invoice

TODAY = date(2026, 11, 6)
FIBERNET = "29AAACN7712E1ZK"
GL_OK = FakeAi(gl=[("6120", "CC-IT-BLR", 0.93, "leased line is a telecom service"),
                   ("6150", "CC-IT-BLR", 0.05, "software"), ("6110", "CC-FAC-BLR", 0.02, "utility")])


def leased_line(taxable="15600", consumer="NF-BLR-0048213"):
    t = D(taxable)
    tax = (t * D("0.09")).quantize(D("0.01"))
    return make_invoice("S01", supplier_gstin=FIBERNET, po_ref=None, invoice_no="NF/BLR/2611-48213",
                        consumer_no=consumer, taxable_total=t, cgst=tax, sgst=tax, grand_total=t + 2 * tax,
                        amount_in_words=None,
                        lines=[Line(description="Internet leased line 100 Mbps, October 2026", hsn_sac="998422",
                                    qty=D("1"), unit="Month", rate=t, taxable=t, gst_rate=D("18"))])


def furniture():
    return make_invoice("S01", po_ref=None, taxable_total=D("86000"), cgst=D("7740"), sgst=D("7740"),
                        grand_total=D("101480"), amount_in_words=None,
                        lines=[Line(description="Conference table, 10-seater", hsn_sac="9403", qty=D("1"),
                                    unit="Nos", rate=D("86000"), taxable=D("86000"), gst_rate=D("18"))])


def run(inv, store, ai=GL_OK):
    ctx = make_ctx(inv, store, ai=ai, today=TODAY, txn_type="po_less")
    return ctx, run_checks("match", ctx, path="po_less")


def codes(findings, status=None):
    return {f.code for f in findings if f.code and (status is None or f.status is status)}


def test_s09_leased_line_all_pass(store):
    ctx, f = run(leased_line(), store)
    assert codes(f, Status.FAIL) == set() and codes(f, Status.WARN) == set()
    assert ctx.scratch["gl"]["gl_code"] == "6120"
    gl = next(x for x in f if x.check == "gl_coding")
    assert [o["gl_code"] for o in gl.data["options"]] == ["6120", "6150", "6110"]
    assert {x.check for x in f} >= {"open_po_exists", "category_allowed", "service_account", "gl_coding",
                                     "amount_anomaly", "po_less_limit"}


def test_s10_furniture_needs_po(store):
    _, f = run(furniture(), store, ai=FakeAi(gl=[("6210", "CC-ADM-BLR", 0.9, "furniture")]))
    pr = next(x for x in f if x.code == "PO_REQUIRED_FOR_CATEGORY")
    assert pr.status is Status.FAIL and "furniture" in pr.detail


def test_open_po_reroutes(store):
    inv = furniture().model_copy(update={"lines": [Line(description="Filing cabinet, 4 drawer", hsn_sac="9403",
                                 qty=D("8"), unit="Nos", rate=D("9800"), taxable=D("78400"), gst_rate=D("18"))]})
    ctx, f = run(inv, store)
    w = next(x for x in f if x.code == "PO_EXISTS_FOR_PO_LESS")
    assert w.status is Status.WARN and ctx.scratch["reroute"] == "standard_po" and w.data["po"] == "PO-4507"
    assert "gl_coding" not in {x.check for x in f}


def test_unknown_service_account(store):
    _, f = run(leased_line(consumer="NF-BLR-9999999"), store)
    assert "UNKNOWN_SERVICE_ACCOUNT" in codes(f, Status.FAIL)


def test_gl_uncertain(store):
    _, f = run(leased_line(), store, ai=FakeAi(gl=[("6120", "CC-IT-BLR", 0.6, "maybe telecom")]))
    assert "GL_CODING_UNCERTAIN" in codes(f, Status.FAIL)


def test_amount_spike_and_limit(store):
    _, f = run(leased_line(taxable="59322"), store)
    spike = next(x for x in f if x.code == "AMOUNT_ANOMALY")
    assert float(spike.data["ratio"]) > 3
    assert "NEEDS_SIGNOFF" in codes(f, Status.FAIL)

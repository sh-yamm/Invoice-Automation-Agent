"""The Streamlit pages: a panel with nothing to show must render nothing, not crash the page."""
import streamlit as st

from ui import common, invoice_view


def test_an_empty_panel_is_skipped_instead_of_crashing(monkeypatch):
    calls = []

    def strict_html(body):
        if not body:
            raise st.errors.StreamlitAPIException("`st.html` body cannot be empty")
        calls.append(body)

    monkeypatch.setattr(common.st, "html", strict_html)
    common.html("")
    common.html(invoice_view.ledger_panel([]))      # no PO-balance finding: nothing to show
    common.html("<p>shown</p>")
    assert calls == ["<p>shown</p>"]


# ---------- whole screens, rendered by Streamlit's test runner (the app's own storage; read-only checks) ----------

from streamlit.testing.v1 import AppTest  # noqa: E402

from ap_agent.core.config import REPO_ROOT  # noqa: E402

APP = str(REPO_ROOT / "streamlit_app.py")


def _run(**params):
    at = AppTest.from_file(APP, default_timeout=120)
    for k, v in params.items():
        at.query_params[k] = v
    return at.run()


def _text(at) -> str:
    return " ".join([x.proto.body for x in at.get("html")] + [m.value for m in at.markdown] + [c.value for c in at.caption])


def test_home_is_an_inbox_of_trails():
    at = _run()
    assert not at.exception
    t = _text(at)
    assert "Needs you" in t and "PO-4518" in t and "Sample Client" in t
    assert "In production, invoices arrive by email" in t


def test_process_an_invoice_starts_by_choosing_the_po():
    at = _run()
    next(b for b in at.button if b.label == "Process an invoice").click().run()
    assert not at.exception
    po_pick = at.selectbox(key="process_po")
    assert any("PO-4518" in str(o) for o in po_pick.options)
    assert any("let the agent find it" in str(o) for o in po_pick.options)
    # a demo invoice can also be run live (real model calls), S18 by default
    assert at.selectbox(key="live_sample").value == "S18"
    assert any(b.label == "Run live" for b in at.button)


def test_every_trail_page_renders():
    from ui import engine
    keys = [t["key"] for t in engine.get("/api/trails")]
    for key in keys:
        at = _run(trail=key)
        assert not at.exception, (key, at.exception[0].value if at.exception else "")


def test_selecting_the_po_shows_its_document():
    at = _run(trail="PO-4518", doc="po:PO-4518")
    assert not at.exception and at.get("imgs")


def _records_app():
    import os
    import sys
    root = os.path.dirname(os.getcwd())  # tests run from backend/
    sys.path[:0] = [root, os.path.join(root, "backend", "src")]
    from ui import style
    from ui.records import records_page
    style.apply()
    records_page()


def test_records_page_refuses_an_invalid_gstin():
    at = AppTest.from_function(_records_app, default_timeout=120).run()
    assert not at.exception
    at.text_input(key="nv_name").input("Test Traders")
    at.text_input(key="nv_gstin").input("29ABCDE1234F1Z0")
    at.text_input(key="nv_why").input("trying it")
    next(b for b in at.button if b.label == "Add and approve vendor").click().run()
    assert any("GSTIN" in e.value for e in at.error)


# ---------- plain words, never reason codes ----------

def test_decision_card_names_the_reason_not_its_code():
    case = {"outcome": 2, "primary_code": "PRICE_VARIANCE", "why": "Billed 5% more.", "owner": "Procurement",
            "next_step": "Confirm the rate.", "also": [], "human_actions": []}
    out = invoice_view.decision_card(case)
    assert "Price above the agreed PO rate" in out and "PRICE_VARIANCE" not in out


def test_a_persons_decision_has_a_plain_label():
    case = {"outcome": 0, "primary_code": "SIGNED_OFF", "why": "Signed off.", "owner": "No one", "next_step": "Pay.",
            "also": [], "human_actions": [{"actor": "Finance controller", "action": "sign_off"}]}
    out = invoice_view.decision_card(case)
    assert "SIGNED_OFF" not in out and "Signed off by a person" in out


def test_check_list_shows_no_reason_codes():
    from ui.parts import check_log
    f = {"stage": "match", "status": "fail", "code": "PRICE_VARIANCE", "title": "Price above tolerance", "detail": "5% more",
         "outcome": 2}
    assert "PRICE_VARIANCE" not in check_log([f])


def _edge_app():
    from ui import style
    from ui.edge_cases import edge_cases_page
    style.apply()
    edge_cases_page()


def test_edge_cases_page_lists_the_four_cases_with_run_buttons():
    at = AppTest.from_function(_edge_app, default_timeout=120).run()
    assert not at.exception
    import html as htmlmod
    body = htmlmod.unescape(" ".join(e.body for e in at.get("html")))
    for t in ("A split PO runs out of balance", "The vendor's bank account has changed",
              "The same invoice, sent again with a new number", "One purchase, split to stay under the approval limit"):
        assert t in body
    assert "SPLIT_BELOW_LIMIT" not in body and "Invoices split to stay under the approval limit" in body
    assert sum(b.label == "Run this invoice" for b in at.button) == 4


# ---------- the reviewing agent's full reasoning, one click away ----------

def test_the_review_reasoning_is_found_among_the_model_calls():
    c = {"llm_calls": [{"node": "extract", "reasoning": "reading the page"},
                       {"node": "agent_review", "reasoning": "First I check the bank account <b>matches</b>."}]}
    assert invoice_view.review_reasoning(c) == "First I check the bank account <b>matches</b>."
    assert invoice_view.review_reasoning({"llm_calls": [{"node": "extract", "reasoning": "x"}]}) is None


def test_the_reasoning_panel_is_collapsed_and_escaped():
    out = invoice_view.reasoning_panel("Step 1 <script>alert(1)</script>")
    assert out.startswith("<details") and "<summary>The model's full reasoning</summary>" in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert invoice_view.reasoning_panel(None) == ""


def test_a_demo_invoice_run_from_the_dialog_uses_the_po_it_prints():
    """Not whatever PO happens to be selected in step 1 (that held S01 as 'uploaded to a different PO')."""
    from ui.process import demo_run
    at = _run()
    next(b for b in at.button if b.label == "Process an invoice").click().run()
    assert at.selectbox(key="process_po").value == "find"  # an upload never silently claims the first PO
    assert demo_run({"id": "S01", "po": "PO-4501"}, "normal") == {"pace": "normal", "sample_id": "S01",
                                                                   "assigned_po": "PO-4501"}
    assert demo_run({"id": "S08", "po": None}, "demo") == {"pace": "demo", "sample_id": "S08"}

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

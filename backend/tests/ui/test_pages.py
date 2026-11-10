"""The Streamlit pages: a panel with nothing to show must render nothing, not crash the page."""
import streamlit as st

from ui import pages


def test_an_empty_panel_is_skipped_instead_of_crashing(monkeypatch):
    calls = []

    def strict_html(body):
        if not body:
            raise st.errors.StreamlitAPIException("`st.html` body cannot be empty")
        calls.append(body)

    monkeypatch.setattr(pages.st, "html", strict_html)
    pages.html("")
    pages.html(pages.ledger_panel([]))      # no PO-balance finding: nothing to show
    pages.html("<p>shown</p>")
    assert calls == ["<p>shown</p>"]

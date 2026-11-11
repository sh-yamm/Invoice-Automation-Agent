"""Shared by the pages: rendering HTML pieces safely, links between pages, the footer."""
from __future__ import annotations

import streamlit as st

FOOT = ('<div class="foot">Zamp Invoice Agent · accounts payable for Sample Client Retail Pvt Ltd (demo company) · '
        'every decision traced to a rule</div>')
EMAIL_NOTE = ("In production, invoices arrive by email and are processed automatically; purchase orders and "
              "goods receipts come from the company's ERP. Here you upload the invoice.")


def html(s: str) -> None:
    """Render an HTML piece; a panel with nothing to show returns "" and is skipped (st.html refuses empty bodies)."""
    if s and s.strip():
        st.html(s)


PAGES: dict = {}  # filled by streamlit_app.py: the navigation's pages, by name


def open_trail(trail: str | None, doc: str | None = None) -> None:
    """Open a PO trail (and a document in it) on the Purchase orders page, from whichever page we are on."""
    params = {k: v for k, v in {"trail": trail, "doc": doc}.items() if v}
    page = PAGES.get("orders")
    if page is None:  # a page rendered on its own (tests)
        go(**params)
    st.switch_page(page, query_params=params)


def go(**params) -> None:
    """Open another view: trail=<key>, doc=<type:ref>. No params: the inbox."""
    st.query_params.clear()
    for k, v in params.items():
        if v:
            st.query_params[k] = v
    st.rerun()


PEOPLE = {"APPROVED_BY_PERSON": "Approved by a person", "SIGNED_OFF": "Signed off by a person",
          "REJECTED_BY_PERSON": "Rejected by a person"}


def reason_title(code: str | None) -> str:
    """A reason's plain name from the rulebook (the app never shows the code itself)."""
    if not code:
        return ""
    if code in PEOPLE:
        return PEOPLE[code]
    from ui import engine
    titles = {r["code"]: r.get("title") or r["code"] for r in engine.get("/api/aop")["reasons"]}
    return titles.get(code, code.replace("_", " ").capitalize())

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


def go(**params) -> None:
    """Open another view: trail=<key>, doc=<type:ref>. No params: the inbox."""
    st.query_params.clear()
    for k, v in params.items():
        if v:
            st.query_params[k] = v
    st.rerun()

"""Zamp Invoice Agent, Streamlit edition: the same agent and API as the React app, in one Python process.

Run locally:   py -3.11 -m streamlit run streamlit_app.py
Streamlit Community Cloud: point the app at this file and add NVIDIA_API_KEY to the app's secrets.
"""
import streamlit as st

st.set_page_config(page_title="Zamp Invoice Agent", page_icon=":material/receipt_long:", layout="wide")

from ui import pages, style  # noqa: E402

style.apply()
nav = st.navigation([
    st.Page(pages.invoices_page, title="Invoices", icon=":material/receipt_long:", url_path="invoices", default=True),
    st.Page(pages.rules_page, title="Rulebook", icon=":material/gavel:", url_path="rules"),
    st.Page(pages.records_page, title="Company records", icon=":material/inventory_2:", url_path="records"),
], position="top")
nav.run()

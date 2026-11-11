"""Zamp Invoice Agent: accounts payable for a demo company, as purchase-order trails.

Run locally:   py -3.11 -m streamlit run streamlit_app.py
Streamlit Community Cloud: point the app at this file and add NVIDIA_API_KEY to the app's secrets.
"""
import streamlit as st

st.set_page_config(page_title="Zamp Invoice Agent", page_icon=":material/receipt_long:", layout="wide")

from ui import style  # noqa: E402
from ui.home import home_page  # noqa: E402
from ui.pages import rules_page  # noqa: E402
from ui.records import records_page  # noqa: E402
from ui.trail_page import trail_page  # noqa: E402


def purchase_orders() -> None:
    key = st.query_params.get("trail")
    if key:
        trail_page(key, st.query_params.get("doc"))
    else:
        home_page()


style.apply()
nav = st.navigation([
    st.Page(purchase_orders, title="Purchase orders", icon=":material/receipt_long:", url_path="orders", default=True),
    st.Page(rules_page, title="Rulebook", icon=":material/gavel:", url_path="rules"),
    st.Page(records_page, title="Company records", icon=":material/inventory_2:", url_path="records"),
], position="top")
nav.run()

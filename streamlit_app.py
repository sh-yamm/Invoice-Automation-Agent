"""Zamp Invoice Agent: accounts payable for a demo company, as purchase-order trails.

Run locally:   py -3.11 -m streamlit run streamlit_app.py
Streamlit Community Cloud: point the app at this file and add NVIDIA_API_KEY to the app's secrets.
"""
import sys
from pathlib import Path

import streamlit as st

# Streamlit re-runs this script on every interaction but keeps imported modules. After a deploy (Streamlit Cloud
# hot-reloads without restarting) the ui/ and samples/ modules would be stale and the new code would import names
# they don't have. When any of their files changes, drop them so they are imported fresh. (ui/engine.py does the
# same for the backend.)
_FILES = sorted(Path(__file__).parent.glob("ui/*.py")) + sorted(Path(__file__).parent.glob("samples/*.py"))
_STAMP = "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in _FILES)
if getattr(sys, "_ap_ui_stamp", None) != _STAMP:  # first run in a fresh process: nothing to drop yet
    for _name in [m for m in sys.modules if m.split(".")[0] in ("ui", "samples")]:
        del sys.modules[_name]
sys._ap_ui_stamp = _STAMP

st.set_page_config(page_title="Zamp Invoice Agent", page_icon=":material/receipt_long:", layout="wide")

from ui import style  # noqa: E402
from ui.common import PAGES  # noqa: E402
from ui.edge_cases import edge_cases_page  # noqa: E402
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
PAGES["orders"] = st.Page(purchase_orders, title="Purchase orders", icon=":material/receipt_long:", url_path="orders",
                          default=True)
nav = st.navigation([
    PAGES["orders"],
    st.Page(edge_cases_page, title="Edge cases", icon=":material/report:", url_path="edge-cases"),
    st.Page(rules_page, title="Rulebook", icon=":material/gavel:", url_path="rules"),
    st.Page(records_page, title="Company records", icon=":material/inventory_2:", url_path="records"),
], position="top")
nav.run()

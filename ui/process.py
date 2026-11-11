"""Starting work: process an invoice against a chosen PO (or let the agent find it), and raise a purchase order."""
from __future__ import annotations

from datetime import date
from html import escape as h

import streamlit as st

from ui import engine
from ui.common import EMAIL_NOTE, go, open_trail
from ui.parts import OUTCOME, inr

from samples.edge_cases import EDGE_CASES  # noqa: E402

EDGE = {c["sample"] for c in EDGE_CASES}
FIND = "find"  # "No PO / not sure: let the agent find it"


def _po_options() -> dict[str, str]:
    """Open POs (and contracts' blanket POs) with what is left, plus the let-the-agent-find-it choice."""
    trails = [t for t in engine.get("/api/trails") if t["kind"] in ("po", "contract") and t.get("po_status") != "closed"]
    trails.sort(key=lambda t: t["key"])
    opts = {t["key"]: f'{t["key"]} · {t["vendor"]} · {inr(t["money"]["left"], 0)} left' for t in trails}
    return {**opts, FIND: "No PO / not sure: let the agent find it"}


def _start(data: dict, files: dict | None = None) -> None:
    try:
        r = engine.post("/api/cases", data=data, files=files)
    except engine.ApiError as e:
        st.error(str(e))
        return
    po = data.get("assigned_po")
    case = engine.get(f"/api/cases/{r['case_id']}")
    from ap_agent.api.trails import case_key  # the trail this invoice lands in
    key = po or case_key({**case, "findings": []}, engine.ctx().deps.repo)
    open_trail(key, f"invoice:{r['case_id']}")


@st.dialog("Process an invoice", width="large")
def process_dialog(fixed_po: str | None = None) -> None:
    st.caption(EMAIL_NOTE)
    opts = _po_options()
    keys = list(opts)
    st.markdown("**Step 1 · Which purchase order is this invoice for?**")
    po = st.selectbox("Purchase order", keys, index=keys.index(fixed_po) if fixed_po in keys else 0,
                      format_func=opts.get, key="process_po", label_visibility="collapsed",
                      help="Pick the PO the vendor is billing. If you're not sure, the agent works it out from the "
                           "PO number printed on the invoice, or from the vendor's open POs.")
    assigned = None if po == FIND else po
    st.markdown("**Step 2 · The vendor's invoice**")
    demo = st.toggle("Demo mode", key="demo_mode",
                     help="Slows the stages down so you can follow each check as it runs. Without it, demo invoices "
                          "finish in about a second, because their model replies are recorded.")
    data = {"pace": "demo" if demo else "normal", **({"assigned_po": assigned} if assigned else {})}
    up = st.file_uploader("Upload the invoice PDF", type=["pdf"])
    if up is not None and st.button("Process invoice", type="primary"):
        _start(data, files={"file": (up.name, up.getvalue(), "application/pdf")})
    samples = engine.get("/api/samples")
    mine = [s for s in samples if assigned and s.get("po") == assigned]
    rest = [s for s in samples if s not in mine]
    for title, group in (("For this PO", mine), ("Other demo invoices" if mine else "Or pick a demo invoice", rest)):
        if not group:
            continue
        st.markdown(f"**{title}**")
        for s in group:
            cls, label, _ = OUTCOME[s["expected_outcome"]]
            c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
            tag = ' <span class="st-chip running">Edge case</span>' if s["id"] in EDGE else ""
            c1.html(f'<div><b>{h(s["id"])} · {h(s["title"])}</b>{tag}<div class="note">{h(s["blurb"])} · {h(s["vendor"])}, '
                    f'{inr(s["total"], 0)}{" · prints " + h(s["po"]) if s.get("po") else " · no PO printed"} · expected '
                    f'<span class="st-chip {cls}">{label}</span></div></div>')
            if c2.button("Run", key=f"run-{s['id']}", width="stretch"):
                _start({**data, "sample_id": s["id"]})
    st.divider()
    if st.button("Reset demo data", help="Restore the 38 past invoices and the company records; removes everything run since."):
        n = engine.post("/api/demo/reset")["cases"]
        st.success(f"Restored {n} past invoices and the company records.")
        go()


@st.dialog("Raise a purchase order", width="large")
def raise_po_dialog() -> None:
    st.caption("Raising a PO is a person's decision. The agent then matches every invoice against it. "
               "In production the PO is emailed to the vendor; here it is added to the records.")
    vendors = [v for v in engine.get("/api/data/vendors") if v["status"] == "active"]
    names = {v["vendor_id"]: f'{v["name"]} ({v["gstin"]})' for v in vendors}
    vendor = st.selectbox("Vendor (approved vendors only)", list(names), format_func=names.get, key="po_vendor")
    a, b = st.columns(2)
    po_type = a.selectbox("For", ["goods", "services"], format_func=str.capitalize, key="po_type",
                          help="Goods are matched 3 ways (PO, goods receipt, invoice); services 2 ways.")
    po_date = b.date_input("PO date", value=date.today(), key="po_date")
    st.markdown("**Lines**")
    lines = st.data_editor([{"description": "", "hsn_sac": "", "qty": 1.0, "unit": "Nos", "rate": 0.0, "gst_rate": 18.0}],
                           num_rows="dynamic", key="po_lines", width="stretch",
                           column_config={"description": "Item", "hsn_sac": "HSN/SAC", "qty": "Quantity",
                                          "unit": "Unit", "rate": "Rate (₹)", "gst_rate": "GST %"})
    why = st.text_input("Why is this PO being raised?", key="po_why", placeholder="For example: stock for the new store")
    if st.button("Raise PO", type="primary"):
        body = {"vendor_id": vendor, "po_type": po_type, "po_date": po_date.isoformat(), "actor": "Buyer",
                "why": why, "lines": [{k: str(v) for k, v in l.items()} for l in lines if l.get("description")]}
        try:
            po = engine.post("/api/pos", json=body)["po_number"]
        except engine.ApiError as e:
            st.error(str(e))
            return
        open_trail(po, f"po:{po}")

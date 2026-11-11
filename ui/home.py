"""The inbox: one row per purchase-order trail, the ones waiting for a person first."""
from __future__ import annotations

from html import escape as h

import streamlit as st

from ui import engine
from ui.common import EMAIL_NOTE, FOOT, go, html
from ui.parts import ago, day, hero, inr, lakh

KIND = {"po": "Purchase order", "contract": "Contract", "no_po": "Bills without a PO", "unmatched": "Not matched"}


def kpi_strip(k: dict) -> str:
    avg = f"{round(k['avg_handling_seconds'])} s" if k.get("avg_handling_seconds") is not None else "—"
    cards = [(k["processed"], "Invoices processed", f"{lakh(k['total_inr'])} in total"),
             (f"{round(k['touchless_pct'])}%", "Done with no person",
              f"{k['touchless']} of {k['processed']}" if k["processed"] else "none yet"),
             (k["exceptions"], "Exceptions caught", "each with a reason and an owner"),
             (lakh(k["protected_inr"]), "Stopped as fraud or duplicate", f"{k['protected_cases']} invoices"),
             (avg, "Average handling time", "a manual AP team takes about 9 days")]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div><div class="d">{d}</div></div>'
        for v, l, d in cards) + "</div>"


def _row(t: dict) -> str:
    money = t.get("money")
    left = f'{inr(money["left"], 0)} left of {inr(money["ordered"], 0)}' if money else ""
    if t["needs_you"]:
        status = '<span class="st-chip hold">! Needs you</span>'
        what = f'<b>{h(t["needs_you"].get("owner") or "Review")}:</b> {h(t["needs_you"]["reason"])}'
        when = ago(t["needs_you"]["since"])
    else:
        status = ('<span class="st-chip approved">✓ Closed</span>' if t["status"] == "closed"
                  else '<span class="st-chip running">Open</span>')
        latest = t.get("latest") or {}
        what = h(latest.get("text") or "No activity yet")
        when = day(latest.get("date")) if latest.get("date") else ""
    href = f'?trail={h(t["key"])}'
    return (f'<a class="trow{" urgent" if t["needs_you"] else ""}" href="{href}" target="_self">'
            f'<span class="tkey"><b class="mono">{h(t["title"])}</b><small>{h(KIND[t["kind"]])}</small></span>'
            f'<span class="tvendor">{h(t["vendor"])}<small>{t["invoices"]} invoice{"s" if t["invoices"] != 1 else ""}</small></span>'
            f'<span class="twhat">{what}<small>{when}</small></span>'
            f'<span class="tright">{status}<small>{left}</small></span></a>')


def home_page() -> None:
    old = st.query_params.get("id")  # links from before trails: open the invoice inside its trail
    if old:
        from ap_agent.api.trails import case_key
        case = engine.ctx().deps.store.get_case(old)
        if case:
            go(trail=case_key(case, engine.ctx().deps.repo), doc=f"invoice:{old}")
    html(hero("Sample Client Retail (demo company) · accounts payable", "Purchase orders and their invoices",
              "Each row is one purchase order and everything that happened on it: the PO sent to the vendor, deliveries, "
              "the vendor's invoices, the agent's checks and decisions. People raise POs and review what the agent flags; "
              "the agent does the rest."))
    a, b, _ = st.columns([1.2, 1, 3])
    if a.button("Process an invoice", type="primary", icon=":material/upload_file:", width="stretch"):
        from ui.process import process_dialog
        process_dialog()
    if b.button("Raise a PO", icon=":material/add_shopping_cart:", width="stretch"):
        from ui.process import raise_po_dialog
        raise_po_dialog()
    st.caption(EMAIL_NOTE)
    inbox()


@st.fragment(run_every=5)
def inbox() -> None:
    if st.query_params.get("trail"):
        return
    a, b = st.columns([3, 1.4], vertical_alignment="bottom")
    period = b.segmented_control("Period", ["This week", "All time"], default="This week", key="period",
                                 label_visibility="collapsed") or "This week"
    a.html(f'<div class="h2">{period}</div>')
    html(kpi_strip(engine.get("/api/kpis", days=7 if period == "This week" else None)))
    trails = engine.get("/api/trails")
    needs = [t for t in trails if t["needs_you"]]
    rest = [t for t in trails if not t["needs_you"]]
    html(f'<div class="h2">Needs you <span class="count">{len(needs)}</span></div>'
         + (f'<div class="tlist">{"".join(_row(t) for t in needs)}</div>' if needs else
            '<div class="allclear">✓ Nothing is waiting for a person.</div>'))
    html(f'<div class="h2">All trails <span class="count">{len(rest)}</span></div>'
         f'<div class="tlist">{"".join(_row(t) for t in rest)}</div>')
    html(FOOT)

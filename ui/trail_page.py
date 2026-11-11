"""One purchase-order trail: the timeline of everything that happened on the left, the selected document on the right."""
from __future__ import annotations

from html import escape as h

import streamlit as st

from ui import engine
from ui.common import EMAIL_NOTE, FOOT, go, html
from ui.home import KIND
from ui.invoice_view import show_invoice
from ui.parts import day, hero, inr

DOT = {"contract": "✍", "po": "▤", "grn": "⬇", "invoice": "₹", "check": "…", "decision": "⚖", "person": "◉",
       "waiting": "!"}
SIDE = {"contract": "client", "po": "client", "grn": "client", "invoice": "vendor", "check": "agent", "decision": "agent",
        "person": "person", "waiting": "person"}


def _doc_of(e: dict) -> str | None:
    return f'{e["doc"]["type"]}:{e["doc"]["ref"]}' if e.get("doc") else None


def _default_doc(t: dict) -> str | None:
    if t.get("needs_you"):
        return f'invoice:{t["needs_you"]["case_id"]}'
    docs = [_doc_of(e) for e in t["events"] if e.get("doc")]
    return docs[-1] if docs else None


def timeline(t: dict, selected: str | None) -> str:
    items = []
    for i, e in enumerate(t["events"]):
        doc = _doc_of(e)
        sel = " sel" if doc and doc == selected and (i == len(t["events"]) - 1 or _doc_of(t["events"][i + 1]) != doc
                                                      or e["kind"] in ("po", "grn")) else ""
        body = (f'<span class="tdot {SIDE[e["kind"]]}">{DOT[e["kind"]]}</span><span class="tbody">'
                f'<span class="twhen">{h(day(e["date"])) if e["date"] else "Now"} · {h(e["actor"])}</span>'
                f'<b>{h(e["title"])}</b><small>{h(e.get("detail") or "")}</small></span>')
        href = f'?trail={h(t["key"])}&doc={h(doc)}' if doc else None
        items.append(f'<li class="tev k-{e["kind"]}{sel}">' + (f'<a href="{href}" target="_self">{body}</a>' if href else
                                                           f'<div>{body}</div>') + "</li>")
    return f'<ol class="timeline">{"".join(items)}</ol>'


def _document(kind: str, ref: str) -> None:
    title = {"po": f"Purchase order {ref}, as sent to the vendor", "grn": f"Goods receipt {ref}, from the warehouse"}[kind]
    html(f'<div class="viewer-h"><span class="eyebrow">{"Sent by Sample Client" if kind == "po" else "Recorded on delivery"}</span>'
         f'<div class="h3">{h(title)}</div></div>')
    try:
        png = engine.call("GET", f"/api/documents/{kind}/{ref}.png")
    except engine.ApiError as e:
        st.error(str(e))
        return
    with st.container(border=True):
        st.image(png, width="stretch")


def trail_page(key: str, doc: str | None) -> None:
    if st.button("← All purchase orders", type="tertiary"):
        go()
    try:
        t = engine.get(f"/api/trails/{key}")
    except engine.ApiError:
        st.error(f"There is no trail {key}. A demo reset may have removed it.")
        return
    money = t.get("money")
    chips = [("vendor", t["vendor"])]
    if money:
        chips += [("ordered", inr(money["ordered"], 0)), ("billed", inr(money["billed"], 0)), ("left", inr(money["left"], 0))]
    if t.get("po_type"):
        chips.append(("match", "3-way: PO, receipt, invoice" if t["po_type"] == "goods" else "2-way: PO, invoice"))
    status = ("Waiting for you: " + (t["needs_you"].get("owner") or "review")) if t["needs_you"] else (
        "Closed" if t["status"] == "closed" else "Open")
    html(hero(f'{KIND[t["kind"]]} · {status}', t["title"], "", chips))
    doc = doc or _default_doc(t)
    left, right = st.columns([0.95, 1.6], gap="medium")
    with left:
        html('<div class="h3" style="margin-bottom:6px">What happened, in order</div>' + timeline(t, doc))
        if t["kind"] in ("po", "contract"):
            if st.button("Upload an invoice for this PO", icon=":material/upload_file:", width="stretch"):
                from ui.process import process_dialog
                process_dialog(fixed_po=t["key"])
            st.caption(EMAIL_NOTE)
    with right:
        if not doc:
            st.info("Nothing to show yet: upload the vendor's invoice for this PO.")
        else:
            kind, _, ref = doc.partition(":")
            if kind == "invoice":
                show_invoice(ref)
            elif kind in ("po", "grn"):
                _document(kind, ref)
    html(FOOT)

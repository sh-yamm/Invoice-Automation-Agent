"""Company records: purchase orders and deliveries, the approved-vendor list (people only), contracts, accounts."""
from __future__ import annotations

from html import escape as h

import streamlit as st

from ui import engine
from ui.common import FOOT, html
from ui.parts import chip, day, hero, inr, num


def _change(path: str, body: dict, done: str) -> None:
    try:
        engine.post(path, json=body)
    except engine.ApiError as e:
        st.error(str(e))
        return
    st.success(done)
    st.rerun()


def vendor_controls(vendors: list[dict]) -> None:
    names = {v["vendor_id"]: f'{v["name"]} ({v["vendor_id"]})' for v in vendors}
    with st.expander("Change a vendor: bank details, block or approve", icon=":material/edit:"):
        vid = st.selectbox("Vendor", list(names), format_func=names.get, key="rv_vendor")
        v = next(x for x in vendors if x["vendor_id"] == vid)
        why = st.text_input("Why? (kept with the change)", key="rv_why",
                            placeholder="For example: signed letter from the vendor, confirmed by phone")
        a, b, c = st.columns(3)
        bank = a.text_input("Bank", value=v["bank_name"], key="rv_bank")
        acct = b.text_input("Account number", value=str(v["bank_account"]), key="rv_acct")
        ifsc = c.text_input("IFSC", value=v["ifsc"], key="rv_ifsc")
        x, y = st.columns(2)
        if x.button("Save bank details", key="rv_save", width="stretch"):
            _change(f"/api/vendors/{vid}/bank", {"bank_name": bank, "bank_account": acct, "ifsc": ifsc,
                                                 "actor": "AP lead", "why": why}, "Bank details changed and logged.")
        blocked = v["status"] != "active"
        if y.button("Approve vendor" if blocked else "Block vendor", key="rv_status", width="stretch"):
            _change(f"/api/vendors/{vid}/status", {"status": "active" if blocked else "blocked", "actor": "AP lead",
                                                   "why": why}, "Vendor approved." if blocked else "Vendor blocked.")
    with st.expander("Add a vendor", icon=":material/person_add:"):
        a, b = st.columns(2)
        name = a.text_input("Name", key="nv_name")
        gstin = b.text_input("GSTIN", key="nv_gstin", help="Checked with the GSTIN check digit.")
        addr = st.text_input("Address", key="nv_addr")
        a, b, c = st.columns(3)
        phone = a.text_input("Phone", key="nv_phone")
        email = b.text_input("Email", key="nv_email")
        cat = c.text_input("Buys", value="general", key="nv_cat")
        a, b, c = st.columns(3)
        bank = a.text_input("Bank", key="nv_bank")
        acct = b.text_input("Account number", key="nv_acct")
        ifsc = c.text_input("IFSC", key="nv_ifsc")
        a, b = st.columns(2)
        terms = a.number_input("Pays in (days)", value=30, min_value=0, step=1, key="nv_terms")
        einv = b.toggle("Must send e-invoices (IRN)", key="nv_einv")
        why = st.text_input("Why add them? (kept with the change)", key="nv_why")
        if st.button("Add and approve vendor", type="primary", key="nv_add"):
            _change("/api/vendors", {"name": name, "gstin": gstin, "address": addr, "phone": phone, "email": email,
                                     "bank_name": bank, "bank_account": acct, "ifsc": ifsc, "einvoice_required": einv,
                                     "payment_terms_days": int(terms), "category": cat, "actor": "AP lead", "why": why},
                    "Vendor added and approved.")
    changes = [c for c in engine.get("/api/record-changes") if c["kind"] in
               ("vendor_added", "bank_changed", "vendor_blocked", "vendor_approved")]
    if changes:
        st.markdown("**Changes to the vendor list**")
        html('<table class="tbl"><tr><th>When</th><th>What</th><th>Vendor</th><th>Who</th><th>Why</th></tr>' + "".join(
            f'<tr><td class="sub">{h(day(c["at"]))}</td><td>{h(c["kind"].replace("_", " ").capitalize())}</td>'
            f'<td class="mono">{h(c["ref"] or "")}</td><td>{h(c["actor"] or "")}</td><td>{h(c["why"] or "")}</td></tr>'
            for c in changes) + "</table>")


def records_page():
    html(hero("What every invoice is checked against", "Company records",
              "Sample Client's own records. The agent only reads them; the one thing it updates is how much of each order "
              "has been billed, and only when an invoice is approved."))
    html('<ol class="howbuy">' + "".join(
        f'<li><span class="n">{i:02d}</span><b>{t}</b><span>{d}</span></li>' for i, (t, d) in enumerate([
            ("Sample Client issues a purchase order", "What it wants, how many, at what price."),
            ("The vendor delivers", "The warehouse records a goods receipt for what arrived."),
            ("The vendor sends an invoice", "The agent matches it to the order and the receipt."),
            ("Approved invoices are paid", "The order's balance goes down by the amount billed.")], start=1)) + "</ol>")
    data = {n: engine.get(f"/api/data/{n}") for n in
            ("po_ledger", "purchase_orders", "goods_receipts", "vendors", "contracts", "chart_of_accounts")}
    t1, t2, t3, t4 = st.tabs(["Orders and deliveries", "Vendors", "Contracts", "Expense accounts"])
    with t1:
        st.caption("Every purchase order Sample Client has issued, what has arrived against it, and how much has been billed.")
        cards = []
        for b in data["po_ledger"]:
            lines = [l for l in data["purchase_orders"] if l["po_number"] == b["po_number"]]
            head = lines[0] if lines else {}
            rows = []
            for l in lines:
                got = [g for g in data["goods_receipts"] if g["po_number"] == b["po_number"] and str(g["line_no"]) == str(l["line_no"])]
                acc = sum(num(g["accepted_qty"]) for g in got)
                dl = ('<span class="muted">no delivery needed</span>' if b.get("po_type") != "goods" else
                      f'{acc:,.0f} {h(l["unit"])} <span class="muted">({"; ".join(g["grn_number"] + ", " + day(g["received_date"]) for g in got)})</span>'
                      if got else '<span class="bad">not delivered yet</span>')
                rows.append(f'<tr><td>{h(l["description"])}</td><td class="r">{num(l["qty"]):,.0f} {h(l["unit"])}</td>'
                            f'<td class="r">{inr(l["rate"])}</td><td>{dl}</td></tr>')
            used = num(b.get("used_pct"))
            kind = {"blanket": "Blanket order", "services": "Services"}.get(b.get("po_type"), "Goods")
            cards.append(f'<article class="order"><header><div><b class="mono">{h(b["po_number"])}</b><div class="note">{h(b.get("vendor") or "")}, '
                         f'issued {day(head.get("po_date"))}</div></div><span class="pill">{kind}, {h(head.get("status", "open"))}</span></header>'
                         f'<table class="tbl"><tr><th>Ordered</th><th class="r">Quantity</th><th class="r">Rate</th><th>Delivered</th></tr>{"".join(rows)}</table>'
                         f'<footer><span class="mini"><span style="width:{min(100, float(used))}%;background:{"var(--rej)" if used >= 100 else "var(--accent)"}"></span></span>'
                         f'Billed <b>{inr(b.get("invoiced"), 0)}</b> of <b>{inr(b.get("value"))}</b>, {inr(b.get("remaining"), 0)} left ({round(used)}% used)</footer></article>')
        html(f'<div class="orders">{"".join(cards)}</div>')
    with t2:
        st.caption("Who Sample Client buys from. The agent checks each invoice's GSTIN and bank account against this list.")
        html('<div class="notice-line">Only people can change this list. The agent flags vendor problems (unknown '
             'vendor, changed bank account, look-alike name) but never adds a vendor or changes bank details.</div>')
        html('<table class="tbl"><tr><th>Vendor</th><th>GSTIN</th><th>Buys</th><th>Bank account on file</th><th>Pays in</th><th>E-invoice</th><th>Status</th></tr>' + "".join(
            f'<tr><td><b>{h(v["name"])}</b><div class="sub">{h(v["vendor_id"])} · {h(v["address"])}</div></td><td class="mono">{h(v["gstin"])}</td>'
            f'<td>{h(str(v["category"]).replace("_", " "))}</td><td>{h(v["bank_name"])} <span class="mono">····{h(str(v["bank_account"])[-4:])}</span></td>'
            f'<td>{h(str(v["payment_terms_days"]))} days</td><td>{"Required" if str(v["einvoice_required"]).lower() in ("true", "1") else "Not required"}</td>'
            f'<td>{chip(0, "done") if v["status"] == "active" else chip(3, "done")}</td></tr>' for v in data["vendors"]) + "</table>")
        vendor_controls(data["vendors"])
    with t3:
        st.caption("Recurring services billed every period. The agent checks the period and the amount.")
        names = {v["vendor_id"]: v["name"] for v in data["vendors"]}
        html('<table class="tbl"><tr><th>Contract</th><th>Vendor</th><th>What for</th><th class="r">Per period</th><th>Runs</th><th>Order</th></tr>' + "".join(
            f'<tr><td class="mono">{h(c["contract_id"])}</td><td>{h(names.get(c["vendor_id"], c["vendor_id"]))}</td><td>{h(c["description"])}</td>'
            f'<td class="r">{inr(c["amount_per_period"])} <span class="sub">{h(c["billing_cycle"])}</span></td>'
            f'<td>{day(c["start_date"])} to {day(c["end_date"])}</td><td class="mono">{h(c["po_number"])}</td></tr>' for c in data["contracts"]) + "</table>")
    with t4:
        st.caption("Where spend without a purchase order (power, internet, rent) is booked.")
        html('<table class="tbl"><tr><th>Account</th><th>Name</th><th>Used for</th><th>Approved by</th></tr>' + "".join(
            f'<tr><td class="mono">{h(str(a["gl_code"]))}</td><td><b>{h(a["name"])}</b></td><td>{h(a["description"])}</td>'
            f'<td>{h(a["budget_owner"])}</td></tr>' for a in data["chart_of_accounts"]) + "</table>")
    html(FOOT)

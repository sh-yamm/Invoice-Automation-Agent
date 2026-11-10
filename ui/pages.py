"""The four views: the invoice list and dashboard (with each invoice's live run view), the rulebook, and
Sample Client's records. All data comes from the agent's own API, called in-process (ui/engine.py)."""
from __future__ import annotations

import io
import uuid
from html import escape as h

import streamlit as st
from PIL import Image, ImageDraw

from ui import engine
from ui.parts import (OUTCOME, TXN, ago, check_log, chip, day, hero, inr, lakh, match_table, num, paper_trail,
                      stage_tiles)

FOOT = '<div class="foot">Zamp Invoice Agent · accounts payable for Sample Client · every decision traced to a rule</div>'


def html(s: str) -> None:
    """Render an HTML piece; a panel with nothing to show returns "" and is skipped (st.html refuses empty bodies)."""
    if s and s.strip():
        st.html(s)


def open_case(case_id: str) -> None:
    st.query_params.clear()
    st.query_params["id"] = case_id
    st.rerun()


# =============== Invoices: dashboard and work queue ===============

@st.dialog("Process an invoice", width="large")
def process_dialog():
    demo = st.toggle("Demo mode", key="demo_mode",
                     help="Slows the stages down so you can follow each check as it runs. Without it, demo invoices "
                          "finish in about a second, because their model replies are recorded.")
    pace = "demo" if demo else "normal"
    up = st.file_uploader("Upload a vendor invoice (PDF)", type=["pdf"])
    if up is not None and st.button("Process this invoice", type="primary"):
        try:
            r = engine.post("/api/cases", files={"file": (up.name, up.getvalue(), "application/pdf")},
                            data={"pace": pace})
            open_case(r["case_id"])
        except engine.ApiError as e:
            st.error(str(e))
    st.markdown("**Or pick a demo invoice.** Each one shows a different thing the agent checks.")
    for s in engine.get("/api/samples"):
        cls, label, _ = OUTCOME[s["expected_outcome"]]
        c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
        c1.html(f'<div><b>{h(s["id"])} · {h(s["title"])}</b><div class="note">{h(s["blurb"])} · {h(s["vendor"])}, '
                f'{inr(s["total"], 0)} · expected <span class="st-chip {cls}">{label}</span></div></div>')
        if c2.button("Run", key=f"run-{s['id']}", width="stretch"):
            r = engine.post("/api/cases", data={"sample_id": s["id"], "pace": pace})
            open_case(r["case_id"])
    st.divider()
    if st.button("Reset demo data", help="Restore the 38 past invoices and remove every invoice run since."):
        n = engine.post("/api/demo/reset")["cases"]
        st.success(f"Restored {n} past invoices.")
        st.rerun()


def kpi_cards(k: dict) -> str:
    o = k["outcomes"]
    parts = [("approved", "Approved", "var(--ok)"), ("needs_signoff", "Needs sign-off", "var(--sign)"),
             ("on_hold", "On hold", "var(--hold)"), ("rejected", "Rejected", "var(--rej)")]
    avg = f"{round(k['avg_handling_seconds'])} s" if k.get("avg_handling_seconds") is not None else "—"
    cards = [
        (k["processed"], "Invoices processed", f"{lakh(k['total_inr'])} in total"),
        (f"{round(k['touchless_pct'])}%", "Done with no person",
         f"{k['touchless']} of {k['processed']} invoices" if k["processed"] else "no invoices yet"),
        (k["exceptions"], "Exceptions caught", "each with a reason and an owner"),
        (lakh(k["protected_inr"]), "Stopped as fraud or duplicate",
         "1 invoice" if k["protected_cases"] == 1 else f"{k['protected_cases']} invoices"),
        (avg, "Average handling time", "a manual AP team takes about 9 days"),
    ]
    c = "".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div><div class="d">{d}</div></div>'
                for v, l, d in cards)
    bar = "".join(f'<div style="flex:{o[key]};background:{col}" title="{lab}: {o[key]}"></div>' for key, lab, col in parts if o[key])
    leg = "".join(f'<span><i style="background:{col}"></i>{lab} <b>{o[key]}</b></span>' for key, lab, col in parts)
    return f'<div class="kpis">{c}</div><div class="outbox"><div class="outbar">{bar}</div><div class="legend">{leg}</div></div>'


def needs_list(cases: list[dict]) -> str:
    needs = [c for c in cases if c.get("outcome") in (1, 2) and c.get("status") != "done"]
    needs.sort(key=lambda c: c["created_at"])
    title = ("Nothing needs you right now" if not needs else "1 invoice needs you" if len(needs) == 1
             else f"{len(needs)} invoices need you")
    rows = "".join(
        f'<a class="need {"signoff" if c["outcome"] == 1 else "hold"}" href="?id={h(c["case_id"])}" target="_self">'
        f'<span class="edge"></span><span class="who">{h(c.get("vendor_name") or c.get("filename") or "")}'
        f'<small><span class="mono">{h(c.get("invoice_no") or c["case_id"])}</span>, {ago(c["created_at"])}</small></span>'
        f'<span class="what"><b>{h(c.get("owner") or "")}:</b> {h(c.get("why") or "")}</span>'
        f'<span class="go">{inr(c.get("grand_total"), 0)} <span class="btn">Review</span></span></a>' for c in needs)
    body = rows or '<div class="allclear">✓ Every processed invoice was approved, rejected or already handled.</div>'
    return (f'<section class="needs"><div class="needs-h"><span class="h3" style="font-size:24px">{title}</span>'
            f'<span class="note">{"Oldest first. Open one to see the evidence and decide." if needs else ""}</span></div>{body}</section>')


def invoice_table(cases: list[dict]) -> str:
    rows = "".join(
        f'<tr><td><a href="?id={h(c["case_id"])}" target="_self">{h(c.get("vendor_name") or c.get("filename") or "Reading…")}</a>'
        f'<div class="sub mono">{h(c.get("invoice_no") or c["case_id"])}</div></td>'
        f'<td>{chip(c.get("outcome"), c.get("status"))}</td><td class="r">{inr(c.get("grand_total"))}</td>'
        f'<td style="min-width:240px">{h(c.get("why") or "")}</td><td>{h(c.get("owner") or "")}</td>'
        f'<td>{TXN.get(c.get("txn_type"), "")}</td><td class="sub" style="white-space:nowrap">{ago(c["created_at"])}</td></tr>'
        for c in cases)
    return (f'<div style="overflow-x:auto"><table class="tbl"><tr><th>Vendor and invoice</th><th>Outcome</th>'
            f'<th class="r">Amount</th><th>Reason</th><th>Owner</th><th>Type</th><th>Received</th></tr>{rows}</table></div>')


def dashboard():
    html(hero("Sample Client · vendor invoices", "Accounts payable",
              "The agent checks every vendor invoice against Sample Client's purchase orders, deliveries and rulebook. "
              "It pays what matches and hands people only the exceptions, each with the reason and the evidence."))
    if st.button("Process an invoice", type="primary", icon=":material/play_arrow:"):
        process_dialog()
    live_lists()


@st.fragment(run_every=4)
def live_lists():
    if st.query_params.get("id"):  # an invoice is open: this auto-refreshing list must not draw under it
        return
    cases = engine.get("/api/cases")
    a, b = st.columns([3, 1.4], vertical_alignment="bottom")
    period = b.segmented_control("Period", ["This week", "All time"], default="This week", key="period",
                                 label_visibility="collapsed") or "This week"
    a.html(f'<div class="h2">{period}</div>')
    k = engine.get("/api/kpis", days=7 if period == "This week" else None)
    html(kpi_cards(k))
    html(needs_list(cases))
    html('<div class="h2">All invoices</div>')
    f1, f2 = st.columns([3, 2])
    labels = {"All": None, "On hold": 2, "Awaiting sign-off": 1, "Approved": 0, "Rejected": 3}
    pick = f1.segmented_control("Outcome", list(labels), default="All", key="out",
                                format_func=lambda x: f"{x} {sum(1 for c in cases if labels[x] is None or c.get('outcome') == labels[x])}",
                                label_visibility="collapsed") or "All"
    types = {"All types": None, **{v: k for k, v in TXN.items()}}
    t = f2.segmented_control("Type", list(types), default="All types", key="typ", label_visibility="collapsed") or "All types"
    rows = [c for c in cases if (labels[pick] is None or c.get("outcome") == labels[pick])
            and (types[t] is None or c.get("txn_type") == types[t])]
    html(invoice_table(rows) if rows else '<p class="note">No invoices with this outcome and type.</p>')
    html(FOOT)


# =============== One invoice: the live run view ===============

def page_with_boxes(case_id: str, findings: list[dict]) -> bytes | None:
    p = engine.page_image(case_id, 1)
    if p is None:
        return None
    img = Image.open(p).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    w, ht = img.size
    for f in findings:
        if f["status"] == "pass":
            continue
        for ev in f.get("evidence") or []:
            if ev.get("box") and (ev.get("page") in (None, 1)):
                x0, y0, x1, y1 = ev["box"]
                col = (179, 33, 63) if f.get("outcome") == 3 else (154, 106, 0)
                draw.rectangle([x0 * w - 4, y0 * ht - 3, x1 * w + 4, y1 * ht + 3], outline=col + (230,), width=4,
                               fill=col + (28,))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def decision_card(c: dict) -> str:
    if c.get("outcome") is None:
        return ('<div class="decision"><div class="verdict" style="color:var(--ink)">Working on it</div><div class="why">'
                'The agent is reading and checking this invoice. Each check appears below the moment it runs, '
                'and the decision lands here.</div></div>')
    cls, label, _ = OUTCOME[int(c["outcome"])]
    also = "".join(f"<li>{h(a)}</li>" for a in c.get("also") or [])
    acted = c.get("human_actions") or []
    done = f'<dt>Decided by</dt><dd>{h(acted[-1]["actor"])}: {h(acted[-1]["action"].replace("_", " "))}</dd>' if acted else ""
    return (f'<div class="decision {cls}"><div style="display:flex;justify-content:space-between;gap:10px">'
            f'<span class="verdict">{label}</span><span class="code">{h(c.get("primary_code") or "")}</span></div>'
            f'<div class="why">{h(c.get("why") or "")}</div><dl class="facts"><dt>Who should act</dt><dd>{h(c.get("owner") or "")}</dd>'
            f'<dt>Next step</dt><dd>{h(c.get("next_step") or "—")}</dd>{done}</dl>'
            f'{f"<div class=note style=margin-top:10px>Also found</div><ul style=margin:4px 0 0>{also}</ul>" if also else ""}</div>')


def ledger_panel(findings: list[dict]) -> str:
    f = next((x for x in findings if x.get("code") in ("AMOUNT_EXCEEDS_PO_BALANCE", "PO_FULLY_INVOICED")), None)
    if not f:
        return ""
    d = f.get("data") or {}
    value, billed, now = num(d.get("po_value")), num(d.get("invoiced")), num(d.get("this_amount"))
    top = max(value, billed + now) or 1
    fits, over = max(0, min(now, value - billed)), max(0, billed + now - value)
    segs = (f'<div style="flex:{billed / top};background:var(--ink-2)"></div>' if billed else "") + \
           (f'<div style="flex:{fits / top};background:var(--hold)"></div>' if fits else "") + \
           (f'<div style="flex:{max(over / top, num("0.04"))};background:var(--rej)"></div>' if over else "")
    return (f'<div class="panel"><div class="pad"><span class="h3" style="font-size:18px">{h(str(d.get("po", "")))}: how much of the order is left</span>'
            f'<div class="ledger">{segs}</div><div class="legend"><span><i style="background:var(--ink-2)"></i>Already billed <b>{inr(billed, 0)}</b></span>'
            f'<span><i style="background:var(--hold)"></i>This invoice <b>{inr(now, 0)}</b></span>'
            f'{f"<span class=bad><i style=background:var(--rej)></i>Over the order by <b>{inr(over, 0)}</b></span>" if over else ""}</div>'
            f'<div class="note">Order value {inr(value, 0)}, of which {inr(max(0, value - billed), 0)} was left before this invoice.</div></div></div>')


def actions(c: dict) -> None:
    if c.get("status") not in ("waiting", "waiting_vendor") or c.get("outcome") not in (1, 2):
        return
    cid = c["case_id"]
    with st.container(border=True):
        st.markdown("**Your decision**")
        locked = c.get("primary_code") in (c.get("locked_codes") or [])
        note = st.text_area("Note, saved in the audit trail" + (" (required: this rule is locked)" if locked else " (optional)"),
                            key=f"note-{cid}", placeholder="For example: new rate agreed with the vendor by email", height=80)
        low = next((f for f in c["findings"] if f.get("code") == "LOW_CONFIDENCE_FIELD"), None)
        field = value = None
        if low:
            vals = (low.get("data") or {}).get("values") or {}
            if vals:
                field = st.selectbox("Field to confirm", list(vals), key=f"fld-{cid}")
                value = st.text_input("Correct value", value=str(vals.get(field, "")), key=f"val-{cid}")
        buttons = ([("sign_off", "Sign off", "primary")] if c["outcome"] == 1 else [("approve_anyway", "Approve anyway", "primary")])
        if low:
            buttons.append(("confirm_field", "Confirm field", "secondary"))
        buttons += [("reject", "Reject", "secondary"), ("ask_vendor", "Ask vendor", "secondary"), ("recheck", "Re-check", "secondary")]
        cols = st.columns(len(buttons))
        for col, (act, label, kind) in zip(cols, buttons):
            if col.button(label, key=f"{act}-{cid}", type=kind, width="stretch"):
                body = {"action": act, "note": note or None, "actor": "AP clerk", "action_key": uuid.uuid4().hex}
                if act == "confirm_field":
                    body.update(field=field, value=value)
                try:
                    engine.post(f"/api/cases/{cid}/actions", json=body)
                    st.rerun()
                except engine.ApiError as e:
                    st.error(str(e))


def case_view(cid: str) -> None:
    if st.button("← All invoices", type="tertiary"):
        st.query_params.clear()
        st.rerun()
    try:
        c = engine.get(f"/api/cases/{cid}")
    except engine.ApiError:
        st.error(f"There is no invoice case {cid}. It may have been removed by a demo reset.")
        return
    if c["status"] == "running":
        live_case(cid)
    else:
        render_case(cid, c, running=False)


@st.fragment(run_every=1.0)
def live_case(cid: str) -> None:
    c = engine.get(f"/api/cases/{cid}")
    render_case(cid, c, running=c["status"] == "running")
    if c["status"] != "running":
        st.rerun()


def render_case(cid: str, c: dict, running: bool) -> None:
    evs = engine.events(cid)
    findings = c["findings"] or [e["payload"] for e in evs if e["type"] == "finding"]
    if running:
        findings = [e["payload"] for e in evs if e["type"] == "finding"]
    replay = any(str(l.get("model", "")).endswith("(cached)") for l in c.get("llm_calls") or [])
    chips = [("invoice", c.get("invoice_no") or cid), ("amount", inr(c.get("grand_total")))]
    if c.get("txn_type"):
        chips.append(("type", TXN[c["txn_type"]]))
    chips.append(("models", "recorded replies" if replay else "live"))
    if c.get("sample_id"):
        chips.append(("demo invoice", c["sample_id"]))
    sub = (f'Classified as {TXN.get(c["txn_type"], "")} ({round((c.get("txn_confidence") or 0) * 100)}% sure): {c.get("txn_why") or ""}'
           if c.get("txn_type") else "")
    html(hero("Live run · checking now" if running else "Invoice case · decided",
              c.get("vendor_name") or c.get("filename") or "Reading the invoice…", sub, chips))
    html('<div class="h2">What the agent is checking</div>' + stage_tiles(evs, findings, c.get("txn_type"), running))
    trail = None
    try:
        trail = engine.get(f"/api/cases/{cid}/trail")
    except engine.ApiError:
        pass
    if trail:
        html(paper_trail(trail))
    left, right = st.columns([0.86, 1.14], gap="medium")
    with left:
        img = page_with_boxes(cid, findings)
        with st.container(border=True):
            st.html('<div class="lbl"><b>The invoice as received.</b> <span class="note">Boxes mark where on the page '
                    'a problem was found.</span></div>' if img else
                    '<div class="note">Opening the PDF…</div>')
            if img:
                st.image(img, width="stretch")
    with right:
        html(decision_card(c))
        actions(c)
        if trail and trail.get("po") and trail.get("invoice"):
            html(match_table(trail))
        html(ledger_panel(findings))
        if c.get("agent_note"):
            with st.expander("The agent's second look"):
                st.caption("After the rules decide, the agent reviews the whole case. It may only make the outcome "
                           "stricter, never approve.")
                st.write(c["agent_note"])
                reasoning = next((l.get("reasoning") for l in c.get("llm_calls") or [] if l.get("node") == "agent_review"), None)
                if reasoning:
                    st.code(reasoning, language=None, wrap_lines=True)
        problems = sum(1 for f in findings if f["status"] == "fail")
        meta = "running…" if running else f"{len(findings)} checks, " + (
            "no problems" if problems == 0 else "1 problem" if problems == 1 else f"{problems} problems")
        html(f'<div class="panel"><div class="panel-h"><span class="h3">Every check, in order</span>'
             f'<span class="note">{meta}</span></div>{check_log(findings)}</div>')
    html(FOOT)


def invoices_page():
    cid = st.query_params.get("id")
    if cid:
        case_view(cid)
    else:
        dashboard()


# =============== Rulebook ===============

SECTIONS = [
    ("What the agent may approve alone", [
        ("authority.auto_approve_limit_inr", "Auto-approve limit", "Above this the agent still checks everything, then asks the finance controller to sign off.", "₹"),
        ("authority.po_less_auto_limit_inr", "PO-less auto limit", "PO-less invoices above this need the budget owner's sign-off.", "₹"),
        ("authority.split_window_days", "Split-invoice window", "Invoices from one vendor inside this window are added up for the limit.", "days")]),
    ("Tolerances", [
        ("tolerance.price.over_pct", "Price tolerance", "How far a billed rate may be above the PO rate.", "%"),
        ("tolerance.price.over_abs_inr", "Price tolerance cap", "The most extra money that tolerance may add on one line.", "₹"),
        ("tolerance.qty_over_ordered_pct", "Quantity over ordered", "Billing for more than was ordered.", "%"),
        ("tolerance.qty_over_received_pct", "Quantity over received", "Billing for more than was delivered and accepted.", "%"),
        ("tolerance.po_balance_over_pct", "PO balance overrun", "Billing beyond the PO value.", "%"),
        ("tolerance.contract_amount_pct", "Contract amount variance", "Recurring invoice vs the contract schedule.", "%")]),
    ("Duplicates", [
        ("duplicates.window_days", "Look-back window", "How far back to compare invoices from the same vendor.", "days"),
        ("duplicates.min_similarity_pct", "Same-lines threshold", "Line similarity at which an invoice counts as a likely resend.", "%")]),
    ("Confidence", [
        ("confidence.min_field", "Minimum field confidence", "Below this the agent asks a person to confirm the field (0–1).", ""),
        ("confidence.po_inference_min", "Minimum to infer a PO", "When no PO number is printed (0–1).", ""),
        ("confidence.classification_min", "Minimum to classify", "Below this the transaction type goes to a person (0–1).", ""),
        ("confidence.gl_coding_min", "Minimum for GL coding", "PO-less GL account choice (0–1).", "")]),
]


def _get(d, path):
    for k in path.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def rules_page():
    aop = engine.get("/api/aop")
    last = aop.get("last_edit") or {}
    html(hero("The rules the agent follows", "Rulebook",
              "Every limit and tolerance the agent uses, in one place. Change a number and the next invoice follows it; "
              "every change is versioned with who made it and why.",
              [("version", str(aop["version"])), ("last change", f'{last.get("editor", "")}, {day(last.get("at"))}'),
               ("why", last.get("why", ""))]))
    changes = {}
    cols = st.columns(2, gap="medium")
    for i, (title, rules) in enumerate(SECTIONS):
        with cols[i % 2].container(border=True):
            st.markdown(f"#### {title}")
            for path, label, help_, unit in rules:
                cur = float(_get(aop, path))
                step = 0.01 if unit == "" else 1.0 if unit in ("₹", "days") else 0.1
                v = st.number_input(f"{label}{f' ({unit})' if unit else ''}", value=cur, step=step, help=help_,
                                    key=f"r-{path}-{aop['version']}", format="%.2f" if step < 1 else "%.0f")
                if v != cur:
                    changes[path] = v
    with st.container(border=True):
        st.markdown("#### Locked rules")
        st.caption("These can never be approved without a written note, and the rulebook cannot unlock them.")
        html("".join(f'<span class="pill" style="margin:0 6px 6px 0">{h(c)}</span>' for c in aop.get("locked") or []))
    why = st.text_input("Why are you changing the rulebook?", placeholder="For example: steel prices are volatile this quarter")
    a, b = st.columns([1, 1])
    if a.button(f"Save {len(changes)} change{'s' if len(changes) != 1 else ''}" if changes else "Save changes",
                type="primary", disabled=not changes, width="stretch"):
        if not why.strip():
            st.error("Say why you are changing the rulebook; it is kept with the version.")
        else:
            try:
                saved = engine.call("PUT", "/api/aop", json={"changes": changes, "editor": "AP lead", "why": why.strip()})
                st.success(f"Saved as version {saved['version']}. The next run follows it.")
                st.rerun()
            except engine.ApiError as e:
                st.error(str(e))
    if b.button("Re-check held invoices under these rules", width="stretch"):
        held = [c for c in engine.get("/api/cases", outcome=2, status="waiting") if not c.get("is_seed")]
        for c in held:
            try:
                engine.post(f"/api/cases/{c['case_id']}/actions",
                            json={"action": "recheck", "actor": "AP lead", "action_key": f"recheck-{c['case_id']}-{aop['version']}"})
            except engine.ApiError:
                pass
        st.success(f"Re-checked {len(held)} held invoice(s)." if held else "No invoices run today are on hold.")
    html(FOOT)


# =============== Company records ===============

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
        html('<table class="tbl"><tr><th>Vendor</th><th>GSTIN</th><th>Buys</th><th>Bank account on file</th><th>Pays in</th><th>E-invoice</th><th>Status</th></tr>' + "".join(
            f'<tr><td><b>{h(v["name"])}</b><div class="sub">{h(v["address"])}</div></td><td class="mono">{h(v["gstin"])}</td>'
            f'<td>{h(str(v["category"]).replace("_", " "))}</td><td>{h(v["bank_name"])} <span class="mono">····{h(str(v["bank_account"])[-4:])}</span></td>'
            f'<td>{h(str(v["payment_terms_days"]))} days</td><td>{"Required" if str(v["einvoice_required"]).lower() in ("true", "1") else "Not required"}</td>'
            f'<td>{chip(0, "done") if v["status"] == "active" else chip(3, "done")}</td></tr>' for v in data["vendors"]) + "</table>")
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

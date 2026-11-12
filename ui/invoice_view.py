"""One invoice inside a trail: the page with evidence boxes, the decision, the reviewer's actions, the match table
and every check. While the agent is still working, the stage tiles and checks refresh every second."""
from __future__ import annotations

import io
import uuid
from html import escape as h

import streamlit as st
from PIL import Image, ImageDraw

from ui import engine
from ui.common import html, reason_title
from ui.parts import OUTCOME, TXN, check_log, inr, match_table, num, stage_tiles

ASSIGNABLE = ("PO_ASSIGNMENT_MISMATCH", "PO_NOT_FOUND")


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
            f'<span class="verdict">{label}</span><span class="code">{h(reason_title(c.get("primary_code")))}</span></div>'
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
        codes = {f.get("code") for f in c["findings"]}
        if codes & set(ASSIGNABLE):
            pos = [p for p in engine.get("/api/trails") if p["kind"] in ("po", "contract") and p.get("po_status") != "closed"]
            same = [p for p in pos if p.get("vendor_id") == c.get("vendor_id")] or pos
            labels = {p["key"]: f'{p["key"]} · {p["vendor"]} · {inr(p["money"]["left"], 0)} left' for p in same}
            a1, a2 = st.columns([3, 1.2], vertical_alignment="bottom")
            target = a1.selectbox("Assign to a PO", list(labels), format_func=labels.get, key=f"assign-{cid}",
                                  help="Moves this invoice to the PO you choose and checks it again against that PO.")
            if a2.button("Assign and re-check", key=f"assign-go-{cid}", width="stretch"):
                try:
                    engine.post(f"/api/cases/{cid}/actions", json={"action": "confirm_field", "field": "po_ref",
                                                                  "value": target, "note": note or None,
                                                                  "actor": "AP clerk", "action_key": uuid.uuid4().hex})
                    st.query_params["trail"] = target
                    st.rerun()
                except engine.ApiError as e:
                    st.error(str(e))
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




def review_reasoning(c: dict) -> str | None:
    """The reviewing agent's full reasoning trace, as the model returned it (the last review, if re-checked)."""
    calls = [l for l in c.get("llm_calls") or [] if l.get("node") == "agent_review" and (l.get("reasoning") or "").strip()]
    return calls[-1]["reasoning"].strip() if calls else None


def reasoning_panel(text: str | None) -> str:
    """Collapsed by default: the model's step-by-step reasoning before its answer."""
    if not text:
        return ""
    return ("<details class=\"reason\"><summary>The model's full reasoning</summary>"
            '<p class="note">Exactly as the model returned it, before its answer. Kept with the case for audit.</p>'
            f'<pre>{h(text)}</pre></details>')


def invoice_panel(cid: str, c: dict, running: bool) -> None:
    evs = engine.events(cid)
    findings = [e["payload"] for e in evs if e["type"] == "finding"] if running else (
        c["findings"] or [e["payload"] for e in evs if e["type"] == "finding"])
    replay = any(str(l.get("model", "")).endswith("(cached)") for l in c.get("llm_calls") or [])
    meta = [c.get("invoice_no") or cid, inr(c.get("grand_total"))]
    if c.get("txn_type"):
        meta.append(TXN[c["txn_type"]])
    meta.append("recorded model replies" if replay else "live models")
    if c.get("sample_id"):
        meta.append(f"demo invoice {c['sample_id']}")
    html(f'<div class="viewer-h"><span class="eyebrow">Invoice from {h(c.get("vendor_name") or "the vendor")}</span>'
         f'<div class="note">{" · ".join(h(str(m)) for m in meta)}</div></div>')
    html(stage_tiles(evs, findings, c.get("txn_type"), running))
    html(decision_card(c))
    actions(c)
    img = page_with_boxes(cid, findings)
    with st.container(border=True):
        html('<div class="lbl"><b>The invoice as received.</b> <span class="note">Boxes mark where on the page a problem '
             'was found.</span></div>' if img else '<div class="note">Opening the PDF…</div>')
        if img:
            st.image(img, width="stretch")
    try:
        trail = engine.get(f"/api/cases/{cid}/trail")
    except engine.ApiError:
        trail = None
    if trail and trail.get("po") and trail.get("invoice"):
        html(match_table(trail))
    html(ledger_panel(findings))
    if c.get("agent_note"):
        with st.expander("The agent's second look"):
            st.caption("After the rules decide, the agent reviews the whole case. It may only make the outcome "
                       "stricter, never approve.")
            st.write(c["agent_note"])
            html(reasoning_panel(review_reasoning(c)))
    problems = sum(1 for f in findings if f["status"] == "fail")
    note = "running…" if running else f"{len(findings)} checks, " + (
        "no problems" if problems == 0 else "1 problem" if problems == 1 else f"{problems} problems")
    html(f'<div class="panel"><div class="panel-h"><span class="h3">Every check, in order</span>'
         f'<span class="note">{note}</span></div>{check_log(findings)}</div>')


@st.fragment(run_every=1.0)
def live_invoice(cid: str) -> None:
    c = engine.get(f"/api/cases/{cid}")
    invoice_panel(cid, c, running=c["status"] == "running")
    if c["status"] != "running":
        st.rerun()


def show_invoice(cid: str) -> None:
    try:
        c = engine.get(f"/api/cases/{cid}")
    except engine.ApiError:
        st.error(f"There is no invoice {cid}. A demo reset may have removed it.")
        return
    if c["status"] == "running":
        live_invoice(cid)
    else:
        invoice_panel(cid, c, running=False)

"""The rulebook: every limit and tolerance the agent uses, editable and versioned."""
from __future__ import annotations

from html import escape as h

import streamlit as st

from ui import engine
from ui.common import FOOT, html
from ui.parts import day, hero

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



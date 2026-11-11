"""Edge cases: the realistic invoices where the happy path would get it wrong, each one runnable from here."""
from __future__ import annotations

from html import escape as h

import streamlit as st

from ui import engine
from ui.common import FOOT, html, open_trail
from ui.parts import OUTCOME, hero


def _run(sample: str, po: str | None, demo: bool) -> None:
    from ui.process import _start
    _start({"sample_id": sample, "pace": "demo" if demo else "normal", **({"assigned_po": po} if po else {})})


def _outcome(c: dict) -> str:
    cls, label, icon = OUTCOME[c["expected_outcome"]]
    return f'<span class="st-chip {cls}">{icon} {h(label)}: {h(c["outcome_title"])}</span>'


def edge_cases_page() -> None:
    data = engine.get("/api/edge-cases")
    html(hero("Beyond the happy path", "Edge cases",
              "Realistic invoices where a straightforward check would approve something it shouldn't. Each one looks "
              "fine on its own; the agent catches it because it looks at the PO's history, the vendor record or the "
              "vendor's other invoices. Run any of them to watch the agent decide."))
    demo = st.toggle("Demo mode", key="edge_demo_mode",
                     help="Slows each check down so you can follow the run. Without it, these demo invoices finish in "
                          "about a second, because their model replies are recorded.")
    for i, c in enumerate(data["cases"], 1):
        with st.container(border=True):
            html(f'<div class="ecase"><div class="ehead"><span class="enum">{i}</span><div><div class="h3">{h(c["title"])}</div>'
                 f'<div class="note">{h(c["vendor"])} · {h(c["po"] or "no PO printed")} · demo invoice {h(c["sample"])}</div></div>'
                 f'<div class="eout">{_outcome(c)}</div></div>'
                 f'<dl class="edl"><dt>The situation</dt><dd>{h(c["scenario"])}</dd>'
                 f'<dt>Why the happy path gets it wrong</dt><dd>{h(c["why_hard"])}</dd>'
                 f'<dt>What the agent does</dt><dd>{h(c["agent_does"])}</dd></dl></div>')
            a, b, _ = st.columns([1.2, 1.2, 3])
            if a.button("Run this invoice", key=f"edge-run-{c['sample']}", type="primary", icon=":material/play_arrow:",
                        width="stretch"):
                _run(c["sample"], c["po"], demo)
            if b.button(f"Open {c['trail']}", key=f"edge-trail-{c['sample']}", icon=":material/timeline:",
                        width="stretch"):
                open_trail(c["trail"])
    html('<div class="h2">Also handled</div><p class="note" style="margin:-4px 0 10px">More situations the agent '
         'treats differently from the happy path, each with a demo invoice.</p>')
    for c in data["also"]:
        x, y = st.columns([5, 1.2], vertical_alignment="center")
        x.html(f'<div><b>{h(c["title"])}</b><div class="note">Demo invoice {h(c["sample"])} · {h(c["vendor"])} · '
               f'expected {_outcome(c)}</div></div>')
        if y.button("Run", key=f"also-run-{c['sample']}", width="stretch"):
            _run(c["sample"], c["po"], demo)
    html(FOOT)

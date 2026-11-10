"""Stage 6 · Controls: duplicates, look-alike vendors, split invoices, approval limits.

controls
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


@node("controls", "controls")
def controls(state, deps):
    found = run_checks("controls", make_ctx(state, deps, load_aop(deps.aop_path)))
    return {"findings": _record(deps, state, found)}

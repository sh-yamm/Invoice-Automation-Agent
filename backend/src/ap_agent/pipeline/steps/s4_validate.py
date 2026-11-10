"""Stage 4 · Validate: GST rules, vendor, tax type, arithmetic, amount in words, dates, e-invoice IRN.

validate
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


@node("validate", "validate")
def validate(state, deps):
    ctx = make_ctx(state, deps, load_aop(deps.aop_path))
    found = run_checks("validate", ctx)
    return {"invoice": _dump(ctx.invoice), "findings": _record(deps, state, found)}

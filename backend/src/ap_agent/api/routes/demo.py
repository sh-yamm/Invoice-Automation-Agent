"""Demo controls."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ap_agent.api.common import J, ctx_of
from ap_agent.storage.seed import reset_demo

router = APIRouter(prefix="/api/demo")


@router.post("/reset")
def reset(request: Request):
    ctx = ctx_of(request)
    n = reset_demo(ctx.deps.store, ctx.seed_path, ctx.deps.files_dir, ctx.deps.checkpoint_path)
    ctx.deps._ai.clear()
    ctx.deps.reload()
    return J({"cases": n})

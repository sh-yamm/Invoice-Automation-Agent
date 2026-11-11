"""Purchase-order trails (see api/trails.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ap_agent.api.common import J, ctx_of
from ap_agent.api.trails import list_trails, trail_detail

router = APIRouter(prefix="/api/trails")


@router.get("")
def trails(request: Request):
    return J(list_trails(ctx_of(request).deps))


@router.get("/{key}")
def trail(request: Request, key: str):
    t = trail_detail(key, ctx_of(request).deps)
    if t is None:
        raise HTTPException(404, f"There is no trail {key}.")
    return J(t)

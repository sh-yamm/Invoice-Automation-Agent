"""The rulebook (AOP): read it, and change its tunable values."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ap_agent.api.common import J, ctx_of
from ap_agent.rulebook.loader import Aop, LockedRuleError, load_aop, outcome_name, save_aop

router = APIRouter(prefix="/api/aop")
EDITABLE = ("authority", "tolerance", "duplicates", "confidence", "po_less_allowed_categories", "locked")


def aop_json(aop: Aop) -> dict:
    d = aop.model_dump(mode="json")
    d["locked"] = sorted(aop.locked)
    d["reasons"] = [{"code": r.code, "title": r.title, "outcome": outcome_name(r.outcome), "owner": r.owner, "explain": r.explain,
                     "next": r.next, "locked": r.code in aop.locked}
                    for r in sorted(aop.reasons.values(), key=lambda r: r.priority)]
    return d


@router.get("")
def get_aop(request: Request):
    return J(aop_json(load_aop(ctx_of(request).deps.aop_path)))


@router.put("")
def put_aop(request: Request, body: dict):
    path = ctx_of(request).deps.aop_path
    current = load_aop(path)
    data = current.model_dump()
    for dotted, value in (body.get("changes") or {}).items():
        keys = dotted.split(".")
        if keys[0] not in EDITABLE:
            raise HTTPException(422, f"'{dotted}' cannot be edited here.")
        node = data
        for k in keys[:-1]:
            if not isinstance(node, dict) or k not in node:
                raise HTTPException(422, f"Unknown rule '{dotted}'.")
            node = node[k]
        if not isinstance(node, dict) or keys[-1] not in node:
            raise HTTPException(422, f"Unknown rule '{dotted}'.")
        node[keys[-1]] = set(value) if keys == ["locked"] else value
    try:
        new = Aop.model_validate(data)
        saved = save_aop(new, path, body.get("editor") or "unknown", body.get("why") or "")
    except LockedRuleError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(422, f"Invalid value: {e}")
    return J(aop_json(saved))

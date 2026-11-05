"""Shared pieces for the HTTP layer: the app context and JSON that keeps money exact."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

from ap_agent.core.constants import OUTCOME_LABELS
from ap_agent.pipeline.graph import Deps, Pipeline


@dataclass
class AppContext:
    deps: Deps
    pipeline: Pipeline
    executor: ThreadPoolExecutor
    seed_path: Path


def ctx_of(request: Request) -> AppContext:
    return request.app.state.ctx


def _default(o):
    if isinstance(o, Decimal):
        return str(o)  # money stays exact: never a float
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def J(obj, status: int = 200) -> Response:
    return Response(json.dumps(obj, default=_default, ensure_ascii=False), status_code=status,
                    media_type="application/json")


def case_json(case: dict, deps: Deps, full: bool = True) -> dict:
    out = {k: v for k, v in case.items() if k not in ("invoice_json", "findings", "events", "tool_calls", "llm_calls",
                                                      "human_actions")}
    out["outcome"] = int(case["outcome"]) if case.get("outcome") is not None else None
    out["outcome_label"] = OUTCOME_LABELS[out["outcome"]] if out["outcome"] is not None else None
    if not full:
        return out
    cid = case["case_id"]
    pages = sorted((deps.files_dir / cid / "pages").glob("page-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    out.update({
        "invoice": json.loads(case["invoice_json"]) if case.get("invoice_json") else None,
        "findings": [f.model_dump(mode="json") for f in case.get("findings", [])],
        "tool_calls": case.get("tool_calls", []),
        "llm_calls": case.get("llm_calls", []),
        "human_actions": case.get("human_actions", []),
        "file": f"/api/cases/{cid}/file" if (deps.files_dir / cid / "original.pdf").exists() else None,
        "pages": [f"/api/cases/{cid}/pages/{p.stem.split('-')[1]}.png" for p in pages],
    })
    return out

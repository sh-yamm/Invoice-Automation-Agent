"""Cases: start one (upload or demo sample), read it, stream its events, act on it."""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ap_agent.api.common import J, case_json, ctx_of
from ap_agent.core.config import REPO_ROOT
from ap_agent.core.models import Outcome
from ap_agent.pipeline.graph import ActionError
from samples.specs import SPECS

router = APIRouter(prefix="/api/cases")
PACE = {"fast": 0, "normal": 280, "presenter": 900}


@router.post("")
async def create_case(request: Request, file: UploadFile | None = File(None), sample_id: str | None = Form(None),
                      pace: str = Form("normal")):
    ctx = ctx_of(request)
    if file is None and not sample_id:
        raise HTTPException(400, "Upload a PDF invoice or choose a demo sample.")
    case_id = "C-" + uuid.uuid4().hex[:6].upper()
    if sample_id:
        if sample_id not in SPECS:
            raise HTTPException(404, f"No demo sample {sample_id}.")
        path, name = REPO_ROOT / "samples" / "pdf" / f"{sample_id}.pdf", f"{sample_id}.pdf"
    else:
        data = await file.read()
        if not data.startswith(b"%PDF-"):
            raise HTTPException(400, "That file is not a PDF. Upload a PDF invoice.")
        tmp = Path(tempfile.mkdtemp()) / "upload.pdf"
        tmp.write_bytes(data)
        path, name = tmp, file.filename or "invoice.pdf"
    ctx.pipeline.prepare(case_id, path, sample_id=sample_id, filename=name)
    ctx.deps.bus.pace_by_case[case_id] = PACE.get(pace, PACE["normal"])
    ctx.executor.submit(ctx.pipeline.run, case_id)
    return J({"case_id": case_id}, 201)


@router.get("")
def list_cases(request: Request, outcome: int | None = None, txn_type: str | None = None, owner: str | None = None,
               status: str | None = None):
    deps = ctx_of(request).deps
    filters = {"outcome": Outcome(outcome) if outcome is not None else None, "txn_type": txn_type, "owner": owner,
               "status": status}
    return J([case_json(c, deps, full=False) for c in deps.store.list_cases(filters)])


@router.get("/{case_id}")
def get_case(request: Request, case_id: str):
    deps = ctx_of(request).deps
    case = deps.store.get_case(case_id)
    if not case:
        raise HTTPException(404, "No such case.")
    return J(case_json(case, deps))


@router.get("/{case_id}/file")
def get_file(request: Request, case_id: str):
    p = ctx_of(request).deps.files_dir / case_id / "original.pdf"
    if not p.exists():
        raise HTTPException(404, "No file for this case.")
    return FileResponse(p, media_type="application/pdf")


@router.get("/{case_id}/pages/{n}.png")
def get_page(request: Request, case_id: str, n: int):
    p = ctx_of(request).deps.files_dir / case_id / "pages" / f"page-{n}.png"
    if not p.exists():
        raise HTTPException(404, "No such page.")
    return FileResponse(p, media_type="image/png")


@router.get("/{case_id}/events")
async def events(request: Request, case_id: str):
    store = ctx_of(request).deps.store
    if store.case_status(case_id) is None:
        raise HTTPException(404, "No such case.")
    last = int(request.headers.get("last-event-id", -1))

    async def stream():
        nonlocal last
        quiet = 0
        while True:
            batch = store.events_since(case_id, last)
            for e in batch:
                last = e["seq"]
                yield f"id: {e['seq']}\nevent: {e['type']}\ndata: {json.dumps(e['payload'], ensure_ascii=False)}\n\n"
            if batch:
                quiet = 0
            elif store.case_status(case_id) != "running":
                quiet += 1
                if quiet > 3:   # finished (or waiting for a person) and nothing new: close the stream
                    yield "event: end\ndata: {}\n\n"
                    return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.15)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{case_id}/actions")
def act(request: Request, case_id: str, body: dict):
    ctx = ctx_of(request)
    if ctx.deps.store.get_case(case_id) is None:
        raise HTTPException(404, "No such case.")
    action = {k: v for k, v in body.items() if k in ("action", "note", "field", "value", "actor", "action_key")}
    action.setdefault("actor", "AP reviewer")
    try:
        case = ctx.pipeline.resume(case_id, action)
    except ActionError as e:
        raise HTTPException(409 if "not waiting" in str(e) else 422, str(e))
    return J(case_json(case, ctx.deps))

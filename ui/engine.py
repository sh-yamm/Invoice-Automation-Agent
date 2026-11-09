"""The agent, running inside the Streamlit process.

The Streamlit pages call the same JSON API as the React app, but in-process through FastAPI's TestClient:
no second server and no network port, which is what Streamlit Community Cloud needs. Cases run on the API's
own worker threads, and the pages poll the case store to show each stage as it happens.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "backend" / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _secrets_to_env() -> None:
    """On Streamlit Cloud the NVIDIA key lives in the app's secrets; locally it comes from .env."""
    try:
        for k in ("NVIDIA_API_KEY",):
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:  # no secrets file locally
        pass


@st.cache_resource(show_spinner="Starting the agent…")
def _engine():
    _secrets_to_env()
    from fastapi.testclient import TestClient

    from ap_agent.api.app import create_app

    app = create_app()
    client = TestClient(app)
    client.__enter__()  # run the app's start-up once; it lives as long as the Streamlit server
    return client, app.state.ctx


class ApiError(Exception):
    pass


def ctx():
    return _engine()[1]


def call(method: str, path: str, **kw):
    r = _engine()[0].request(method, path, **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text
        raise ApiError(detail if isinstance(detail, str) else json.dumps(detail))
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.content


def get(path: str, **params):
    return call("GET", path, params={k: v for k, v in params.items() if v is not None})


def post(path: str, **kw):
    return call("POST", path, **kw)


def events(case_id: str) -> list[dict]:
    """Every event recorded for a case so far (stages started and finished, findings, the decision)."""
    rows = ctx().deps.store.db.query("SELECT seq, type, payload FROM events WHERE case_id = ? ORDER BY seq", (case_id,))
    return [{"seq": r["seq"], "type": r["type"], "payload": json.loads(r["payload"])} for r in rows]


def page_image(case_id: str, n: int) -> Path | None:
    p = ctx().deps.files_dir / case_id / "pages" / f"page-{n}.png"
    return p if p.exists() else None

"""The FastAPI app: REST + server-sent events, and the built web UI.

Run locally (from backend/):  py -3.11 -m uvicorn ap_agent.api.app:app --reload
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI

from ap_agent.core.config import REPO_ROOT, Settings

if str(REPO_ROOT) not in sys.path:  # the demo sample specs live in samples/ at the repo root
    sys.path.insert(0, str(REPO_ROOT))

from ap_agent.ai.gateway import Gateway  # noqa: E402
from ap_agent.api.common import AppContext  # noqa: E402
from ap_agent.api.routes import cases, dashboard, data, demo, records, rulebook, trails  # noqa: E402
from ap_agent.erp.repository import Repository  # noqa: E402
from ap_agent.pipeline.graph import Deps, Pipeline  # noqa: E402
from ap_agent.storage.cases import Store  # noqa: E402
from ap_agent.storage.seed import reset_demo, restore_records  # noqa: E402


def default_deps(s: Settings) -> Deps:
    store = Store(s.storage_dir / "runs.db")
    if not store.list_cases({}):
        reset_demo(store, s.seed_path, s.storage_dir / "files", s.storage_dir / "checkpoints.db")
    if not (s.erp_work_dir / "vendors.csv").exists():
        restore_records(s.erp_dir, s.erp_work_dir)
    return Deps(repo=Repository.load(s.erp_work_dir), store=store, aop_path=s.rulebook_path,
                gateway=Gateway(s, store, s.samples_dir / "cache"), files_dir=s.storage_dir / "files",
                checkpoint_path=s.storage_dir / "checkpoints.db", erp_dir=s.erp_work_dir)


def create_app(deps: Deps | None = None, seed_path: Path | None = None) -> FastAPI:
    s = Settings()
    deps = deps or default_deps(s)
    app = FastAPI(title="Zamp Invoice Agent", version="0.1.0")
    app.state.ctx = AppContext(deps=deps, pipeline=Pipeline(deps), executor=ThreadPoolExecutor(max_workers=2),
                               seed_path=seed_path or s.seed_path)
    for r in (cases.router, rulebook.router, data.router, dashboard.router, demo.router, records.router, trails.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"ok": True}
    return app


class _LazyApp:
    """`uvicorn ap_agent.api.app:app` builds the real app on first use, so importing this module is cheap."""

    def __init__(self):
        self._app = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = _LazyApp()

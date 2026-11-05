"""Run every demo sample through the real pipeline with live models once, recording each model reply
in samples/cache/. After this, demos and end-to-end tests replay the recorded replies.

Usage (repo root):
    py -3.11 samples/seed_cache.py            # all samples, keep existing cache entries
    py -3.11 samples/seed_cache.py S08 S13    # only these
    py -3.11 samples/seed_cache.py --fresh S08  # drop cached replies for S08 first
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend" / "src"), str(ROOT)]

from ap_agent.ai.gateway import Gateway  # noqa: E402
from ap_agent.core.config import Settings  # noqa: E402
from ap_agent.core.models import Status  # noqa: E402
from ap_agent.erp.repository import Repository  # noqa: E402
from ap_agent.pipeline.graph import Deps, Pipeline  # noqa: E402
from ap_agent.storage.cases import Store  # noqa: E402
from ap_agent.storage.seed import reset_demo  # noqa: E402
from samples.specs import SPECS  # noqa: E402

CACHE = ROOT / "samples" / "cache"
sys.stdout.reconfigure(encoding="utf-8")  # the Windows console default can't print ₹


def run(sid: str, fresh: bool) -> bool:
    if fresh:
        for f in CACHE.glob(f"{sid}_*.json"):
            f.unlink()
    s = Settings()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        store = Store(tmp / "runs.db")
        reset_demo(store, s.seed_path)
        deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=s.rulebook_path,
                    gateway=Gateway(s, store, CACHE), files_dir=tmp / "files", checkpoint_path=tmp / "cp.db")
        started = time.time()
        case = Pipeline(deps).start(f"seed-{sid}", ROOT / "samples" / "pdf" / f"{sid}.pdf", sample_id=sid)
        spec = SPECS[sid]
        ok = (case["outcome"], case["primary_code"]) == (spec.expected_outcome, spec.expected_code)
        print(f"{'OK  ' if ok else 'MISS'} {sid} {case['outcome'].name:<13} {case['primary_code']:<36} "
              f"expected {spec.expected_outcome.name} {spec.expected_code}  ({time.time() - started:.0f}s)", flush=True)
        if not ok:
            for f in case["findings"]:
                if f.status is not Status.PASS:
                    print(f"       {f.status.value:<4} {f.code}: {f.detail[:140]}")
            if case.get("agent_note"):
                print(f"       agent: {case['agent_note'][:200]}")
        return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    fresh = "--fresh" in args
    ids = [a for a in args if a != "--fresh"] or sorted(SPECS)
    results = [run(sid, fresh) for sid in ids]
    print(f"\n{sum(results)}/{len(results)} samples reached their expected outcome")

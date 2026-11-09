"""Build the demo's starting history by running the 38 past invoices (samples/history.py) through the real agent.

    py -3.11 scripts/build_history.py            # live models the first time; replays data/seed/cache after
    py -3.11 scripts/build_history.py --fresh H-OLD-05   # drop one case's recorded replies first

It writes Zentra's records for those invoices into data/erp (their POs and goods receipts), prints each PDF,
runs every invoice in date order (one vendor at a time, vendors in parallel), and saves:
    data/seed/history.db      cases, findings, events, model calls, ledgers
    data/seed/checkpoints.db  paused runs, so a person can still act on the held ones
    data/seed/files/<case>/   original.pdf and page images
A demo reset restores exactly this.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend" / "src"), str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")

from ap_agent.ai.gateway import Gateway  # noqa: E402
from ap_agent.core.config import Settings  # noqa: E402
from ap_agent.core.models import Outcome, Status  # noqa: E402
from ap_agent.erp.repository import Repository  # noqa: E402
from ap_agent.pipeline.graph import Deps, Pipeline  # noqa: E402
from ap_agent.storage.cases import Store  # noqa: E402
from samples.generate import generate  # noqa: E402
from samples.history import HISTORY, HISTORY_GRNS, HISTORY_POS  # noqa: E402

SEED = ROOT / "data" / "seed"
CACHE = SEED / "cache"
ERP = ROOT / "data" / "erp"
PO_COLS = ["po_number", "vendor_id", "po_type", "po_date", "status", "line_no", "item_code", "description", "hsn_sac",
           "qty", "unit", "rate", "gst_rate"]
GRN_COLS = ["grn_number", "po_number", "line_no", "received_qty", "accepted_qty", "received_date"]


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def write_erp(erp_dir: Path, *, open_all: bool) -> None:
    """Zentra's records plus the history POs and receipts. During the build every history PO is open (as it was
    when its invoice arrived); in the saved records a settled PO is closed."""
    settled = {c.spec.invoice.po_ref: c.po_status_after for c in HISTORY if c.case_id.startswith("H-OLD")}
    ours = {p.po_number for p in HISTORY_POS}
    pos = [r for r in _rows(erp_dir / "purchase_orders.csv") if r["po_number"] not in ours]
    for p in HISTORY_POS:
        pos.append({"po_number": p.po_number, "vendor_id": p.vendor_id, "po_type": p.po_type,
                    "po_date": p.po_date.isoformat(), "status": "open" if open_all else settled[p.po_number],
                    "line_no": p.line_no, "item_code": p.item_code, "description": p.description, "hsn_sac": p.hsn_sac,
                    "qty": p.qty, "unit": p.unit, "rate": p.rate, "gst_rate": p.gst_rate})
    _write(erp_dir / "purchase_orders.csv", PO_COLS, pos)
    grn_ids = {g.grn_number for g in HISTORY_GRNS}
    grns = [r for r in _rows(erp_dir / "goods_receipts.csv") if r["grn_number"] not in grn_ids]
    grns += [{"grn_number": g.grn_number, "po_number": g.po_number, "line_no": g.line_no, "received_qty": g.qty,
              "accepted_qty": g.qty, "received_date": g.received_date.isoformat()} for g in HISTORY_GRNS]
    _write(erp_dir / "goods_receipts.csv", GRN_COLS, grns)


def main(argv: list[str]) -> int:
    if "--fresh" in argv:
        for cid in [a for a in argv if a != "--fresh"]:
            for f in CACHE.glob(f"{cid}_*.json"):
                f.unlink()
    CACHE.mkdir(parents=True, exist_ok=True)
    write_erp(ERP, open_all=False)
    s = Settings()
    work = Path(tempfile.mkdtemp(prefix="history-"))
    erp = work / "erp"
    shutil.copytree(ERP, erp)
    write_erp(erp, open_all=True)
    pdf_dir = work / "pdf"
    store = Store(work / "runs.db")
    deps = Deps(repo=Repository.load(erp), store=store, aop_path=s.rulebook_path, gateway=Gateway(s, store, CACHE),
                files_dir=work / "files", checkpoint_path=work / "checkpoints.db", erp_dir=erp)
    pipeline = Pipeline(deps)
    print(f"building {len(HISTORY)} history cases in {work}", flush=True)

    by_vendor: dict[str, list] = defaultdict(list)
    for c in HISTORY:  # already in date order
        by_vendor[c.spec.supplier["gstin"]].append(c)
    results: dict[str, tuple] = {}

    def run_vendor(cases):
        for c in cases:
            t0 = time.time()
            pdf = generate(c.spec, pdf_dir)
            case = pipeline.start(c.case_id, pdf, sample_id=c.case_id, filename=f"{c.spec.invoice.invoice_no}.pdf")
            took = case["decided_at"] and (datetime.fromisoformat(case["decided_at"]) - datetime.fromisoformat(case["created_at"]))
            created = c.created_at.isoformat(timespec="seconds")
            decided = (c.created_at + took).isoformat(timespec="seconds") if took else None
            store.db.execute("UPDATE cases SET created_at = ?, decided_at = ?, sample_id = NULL, is_seed = 1 "
                             "WHERE case_id = ?", (created, decided, c.case_id))
            got = (case["outcome"], case["primary_code"])
            ok = got == (c.spec.expected_outcome, c.spec.expected_code) or got in c.also_ok
            if ok and c.human:
                act = "sign_off" if case["outcome"] == Outcome.NEEDS_SIGNOFF else "approve_anyway"
                case = pipeline.resume(c.case_id, {"action": act, "actor": c.human["actor"], "note": c.human["note"],
                                                    "action_key": f"history-{c.case_id}"})
                at = (c.created_at + timedelta(hours=c.human["hours"])).isoformat(timespec="seconds")
                store.db.execute("UPDATE human_actions SET at = ? WHERE case_id = ?", (at, c.case_id))
                # keep the agent's own decision time (the handling-time figure measures the agent, not the person)
                store.db.execute("UPDATE cases SET decided_at = ? WHERE case_id = ?", (decided, c.case_id))
            results[c.case_id] = (ok, case)
            print(f"{'OK  ' if ok else 'MISS'} {c.case_id:<11} {case['outcome'].name if case['outcome'] is not None else '-':<13} "
                  f"{case['primary_code'] or '-':<28} want {c.spec.expected_outcome.name} {c.spec.expected_code} "
                  f"({time.time() - t0:.0f}s)", flush=True)
            if not ok:
                for f in case["findings"]:
                    if f.status is not Status.PASS:
                        print(f"        {f.status.value} {f.code}: {f.detail[:150]}", flush=True)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(run_vendor, by_vendor.values()))

    misses = [cid for cid, (ok, _) in results.items() if not ok]
    print(f"\n{len(results) - len(misses)}/{len(results)} reached their intended outcome")
    if misses:
        print("not saved; fix these and run again:", " ".join(misses))
        return 1

    # Save the snapshot.
    store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for name in ("history.db", "checkpoints.db"):
        (SEED / name).unlink(missing_ok=True)
    src = sqlite3.connect(str(work / "runs.db"))
    dst = sqlite3.connect(str(SEED / "history.db"))
    src.backup(dst)
    dst.execute("VACUUM")
    dst.close()
    src.close()
    cp_src = sqlite3.connect(str(work / "checkpoints.db"))
    cp_dst = sqlite3.connect(str(SEED / "checkpoints.db"))
    cp_src.backup(cp_dst)
    cp_dst.execute("VACUUM")
    cp_dst.close()
    cp_src.close()
    shutil.rmtree(SEED / "files", ignore_errors=True)
    shutil.copytree(work / "files", SEED / "files")
    print(f"saved {len(results)} cases to {SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

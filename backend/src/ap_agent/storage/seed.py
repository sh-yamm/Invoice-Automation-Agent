"""Load the demo's history and reset the demo.

The history is a snapshot of 38 past invoices that were run through the real agent (scripts/build_history.py):
data/seed/history.db (cases, findings, events, ledgers), data/seed/checkpoints.db (paused runs, so people can act
on the held ones) and data/seed/files/<case>/ (original PDF and page images). Without a snapshot, the older
summary-only history.json is loaded instead."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from ap_agent.core.models import Outcome
from ap_agent.storage.cases import Store
from ap_agent.storage.db import TABLES


def seed_history(store: Store, path: Path) -> int:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]
    with store.db.lock:
        store.db.execute("BEGIN")
        try:
            _load(store, cases)
            store.db.execute("COMMIT")
        except Exception:
            store.db.execute("ROLLBACK")
            raise
    return len(cases)


def _load(store: Store, cases: list[dict]) -> None:
    for c in cases:
        store.create_case(c["case_id"], c.get("filename"), c.get("sha256"), None,
                          created_at=c["created_at"], is_seed=True)
        store.set_invoice_summary(
            c["case_id"], vendor_id=c["vendor_id"], vendor_name=c["vendor_name"],
            invoice_no=c["invoice_no"], invoice_no_norm=c["invoice_no_norm"],
            invoice_date=date.fromisoformat(c["invoice_date"]), grand_total=Decimal(c["grand_total"]),
            line_texts=c["line_texts"],
            period_start=_period_start(c))
        store.set_outcome(
            c["case_id"], Outcome[c["outcome"]], c["primary_code"], c.get("why", ""), c.get("owner", ""),
            c.get("next_step", ""), None, c["txn_type"], "tax_invoice", decided_at=c["decided_at"],
            status=c.get("status"))
        for l in c.get("ledger", []):
            store.ledger_write(c["case_id"], l["po_number"], l["line_no"], Decimal(l["qty"]), Decimal(l["amount"]))
        if c.get("period"):
            store.period_write(c["case_id"], c["period"]["contract_id"], date.fromisoformat(c["period"]["period_start"]))


def _period_start(c: dict):
    p = c.get("period_start") or (c.get("period") or {}).get("period_start")
    return date.fromisoformat(p) if p else None


def snapshot_dir(path: Path) -> Path | None:
    d = Path(path) if Path(path).is_dir() else Path(path).parent
    return d if (d / "history.db").exists() else None


def load_snapshot(store: Store, seed: Path, files_dir: Path | None = None, checkpoint_path: Path | None = None) -> int:
    with store.db.lock:
        store.db.execute("ATTACH DATABASE ? AS snap", (str(seed / "history.db"),))
        try:
            store.db.execute("BEGIN")
            for t in TABLES:
                store.db.execute(f"INSERT INTO main.{t} SELECT * FROM snap.{t}")
            store.db.execute("COMMIT")
        except Exception:
            store.db.execute("ROLLBACK")
            raise
        finally:
            store.db.execute("DETACH DATABASE snap")
    if files_dir is not None and (seed / "files").exists():
        shutil.copytree(seed / "files", files_dir, dirs_exist_ok=True)
    if checkpoint_path is not None and (seed / "checkpoints.db").exists():
        _restore_checkpoints(seed / "checkpoints.db", Path(checkpoint_path))
    return store.db.query("SELECT COUNT(*) AS n FROM cases")[0]["n"]


def _restore_checkpoints(src: Path, dst: Path) -> None:
    """Copy the paused runs into the live checkpoint database (same tables the LangGraph saver uses)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(dst), isolation_level=None)
    try:
        con.execute("ATTACH DATABASE ? AS snap", (str(src),))
        for (name, sql) in con.execute("SELECT name, sql FROM snap.sqlite_master WHERE type = 'table'").fetchall():
            con.execute(sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
            con.execute(f"DELETE FROM main.{name}")
            con.execute(f"INSERT INTO main.{name} SELECT * FROM snap.{name}")
        con.execute("DETACH DATABASE snap")
    finally:
        con.close()


def reset_demo(store: Store, path: Path, files_dir: Path | None = None, checkpoint_path: Path | None = None) -> int:
    """Delete every case, ledger row and stored file, then load the history again."""
    with store.db.lock:
        for t in TABLES:
            store.db.execute(f"DELETE FROM {t}")
    if files_dir is not None and Path(files_dir).exists():
        for child in Path(files_dir).iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
    seed = snapshot_dir(path)
    if seed is not None:
        return load_snapshot(store, seed, files_dir, checkpoint_path)
    legacy = Path(path) if Path(path).is_file() else Path(path) / "history.json"
    return seed_history(store, legacy)

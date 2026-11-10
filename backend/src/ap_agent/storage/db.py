"""SQLite connection and schema for our own store (case records, ledgers)."""
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  filename TEXT, sha256 TEXT, sample_id TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  vendor_id TEXT, vendor_name TEXT,
  invoice_no TEXT, invoice_no_norm TEXT, invoice_date TEXT, grand_total TEXT,
  line_texts TEXT, period_start TEXT,
  doc_type TEXT, txn_type TEXT, txn_confidence REAL, txn_why TEXT,
  outcome INTEGER, primary_code TEXT, why TEXT, owner TEXT, next_step TEXT,
  also TEXT, agent_note TEXT, aop_version INTEGER,
  decided_at TEXT, invoice_json TEXT, is_seed INTEGER NOT NULL DEFAULT 0,
  assigned_po TEXT
);
CREATE TABLE IF NOT EXISTS record_changes (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT,
  actor TEXT, why TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS findings (
  case_id TEXT NOT NULL, seq INTEGER NOT NULL, id TEXT NOT NULL, json TEXT NOT NULL,
  PRIMARY KEY (case_id, seq)
);
CREATE TABLE IF NOT EXISTS events (
  case_id TEXT NOT NULL, seq INTEGER NOT NULL, at TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (case_id, seq)
);
CREATE TABLE IF NOT EXISTS tool_calls (
  case_id TEXT NOT NULL, seq INTEGER NOT NULL, at TEXT NOT NULL, node TEXT, tool TEXT, args TEXT, result TEXT,
  PRIMARY KEY (case_id, seq)
);
CREATE TABLE IF NOT EXISTS llm_calls (
  case_id TEXT NOT NULL, seq INTEGER NOT NULL, at TEXT NOT NULL, node TEXT, model TEXT,
  prompt TEXT, response TEXT, reasoning TEXT, latency_ms INTEGER, tokens INTEGER,
  PRIMARY KEY (case_id, seq)
);
CREATE TABLE IF NOT EXISTS human_actions (
  case_id TEXT NOT NULL, action_key TEXT NOT NULL, at TEXT NOT NULL,
  action TEXT NOT NULL, actor TEXT, note TEXT, payload TEXT,
  PRIMARY KEY (case_id, action_key)
);
CREATE TABLE IF NOT EXISTS po_ledger (
  case_id TEXT NOT NULL, po_number TEXT NOT NULL, line_no INTEGER NOT NULL,
  qty TEXT NOT NULL, amount TEXT NOT NULL,
  PRIMARY KEY (case_id, po_number, line_no)
);
CREATE TABLE IF NOT EXISTS period_ledger (
  case_id TEXT NOT NULL, contract_id TEXT NOT NULL, period_start TEXT NOT NULL,
  PRIMARY KEY (case_id, contract_id, period_start)
);
"""

TABLES = ("cases", "findings", "events", "tool_calls", "llm_calls", "human_actions", "po_ledger", "period_ledger",
          "record_changes")

# Columns added after a database may already exist: added in place on open.
ADDED_COLUMNS = {"cases": {"assigned_po": "TEXT"}}


class Db:
    """One shared connection guarded by a lock; the pipeline runs in worker threads."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        for table, cols in ADDED_COLUMNS.items():
            have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col, kind in cols.items():
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")

    def execute(self, sql: str, params=()):
        with self.lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def next_seq(self, table: str, case_id: str) -> int:
        row = self.query(f"SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM {table} WHERE case_id = ?", (case_id,))
        return row[0]["n"]

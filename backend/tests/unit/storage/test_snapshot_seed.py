"""A demo reset restores the processed history: case rows, findings, page images and paused runs."""
import sqlite3

from ap_agent.storage.cases import Store
from ap_agent.storage.seed import reset_demo


def _snapshot(seed_dir):
    src = Store(seed_dir / "build.db")
    src.create_case("H-1", "h1.pdf", "abc", None, created_at="2026-08-01T10:00:00", is_seed=True)
    src.db.execute("UPDATE cases SET invoice_json = ?, status = 'waiting' WHERE case_id = 'H-1'", ('{"po_ref": "PO-1"}',))
    src.db.execute("INSERT INTO po_ledger (case_id, po_number, line_no, qty, amount) VALUES ('H-1','PO-1',1,'2','100')")
    dst = sqlite3.connect(seed_dir / "history.db")
    src.db.conn.backup(dst)
    dst.close()
    page = seed_dir / "files" / "H-1" / "pages" / "page-1.png"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"png")
    cp = sqlite3.connect(seed_dir / "checkpoints.db")
    cp.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, "
               "parent_checkpoint_id TEXT, type TEXT, checkpoint BLOB, metadata BLOB, "
               "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))")
    cp.execute("CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, task_id TEXT, idx INTEGER, "
               "channel TEXT, type TEXT, value BLOB, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))")
    cp.execute("INSERT INTO checkpoints VALUES ('H-1','','c1',NULL,'msgpack',x'00',x'00')")
    cp.commit()
    cp.close()


def test_reset_restores_the_processed_history(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    _snapshot(seed)
    store = Store(tmp_path / "runs.db")
    store.create_case("C-NEW", "x.pdf", "zzz", None)
    files = tmp_path / "files"
    (files / "C-NEW").mkdir(parents=True)
    cp_path = tmp_path / "cp.db"

    n = reset_demo(store, seed, files_dir=files, checkpoint_path=cp_path)

    assert n == 1
    case = store.get_case("H-1")
    assert case["invoice_json"] == '{"po_ref": "PO-1"}' and store.get_case("C-NEW") is None
    assert store.db.query("SELECT amount FROM po_ledger")[0]["amount"] == "100"
    assert (files / "H-1" / "pages" / "page-1.png").read_bytes() == b"png"
    assert not (files / "C-NEW").exists()
    rows = sqlite3.connect(cp_path).execute("SELECT thread_id FROM checkpoints").fetchall()
    assert rows == [("H-1",)]


def test_old_snapshot_without_new_columns_still_loads(tmp_path):
    """A history snapshot written before a column or table was added must still restore."""
    seed = tmp_path / "seed"
    seed.mkdir()
    old = sqlite3.connect(seed / "history.db")
    old.execute("CREATE TABLE cases (case_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, filename TEXT, "
                "status TEXT NOT NULL DEFAULT 'running', is_seed INTEGER NOT NULL DEFAULT 0)")
    old.execute("INSERT INTO cases (case_id, created_at, filename, is_seed) VALUES ('H-OLD', '2026-08-01T10:00:00', 'a.pdf', 1)")
    old.commit()
    old.close()
    store = Store(tmp_path / "runs.db")
    assert reset_demo(store, seed) == 1
    case = store.get_case("H-OLD")
    assert case["filename"] == "a.pdf" and case["assigned_po"] is None

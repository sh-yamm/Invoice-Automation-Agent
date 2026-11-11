"""Purchase-order trails: every invoice under the PO it belongs to, in the order things happened."""
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from ap_agent.ai.gateway import Gateway
from ap_agent.api.app import create_app
from ap_agent.core.config import REPO_ROOT, Settings
from ap_agent.erp.repository import Repository
from ap_agent.pipeline.graph import Deps
from ap_agent.storage.cases import Store
from ap_agent.storage.seed import reset_demo

CACHE = REPO_ROOT / "samples" / "cache"


@pytest.fixture
def client(tmp_path):
    s = Settings()
    erp = tmp_path / "erp"
    shutil.copytree(s.erp_dir, erp)
    store = Store(tmp_path / "runs.db")
    reset_demo(store, s.seed_path)
    deps = Deps(repo=Repository.load(erp), store=store, aop_path=s.rulebook_path,
                gateway=Gateway(s, store, CACHE, offline=True), files_dir=tmp_path / "files",
                checkpoint_path=tmp_path / "cp.db", erp_dir=erp)
    with TestClient(create_app(deps, seed_path=s.seed_path)) as c:
        yield c


def _done(client, cid):
    for _ in range(300):
        if client.get(f"/api/cases/{cid}").json()["status"] != "running":
            return
        time.sleep(0.2)
    raise AssertionError("case did not finish")


def test_every_po_is_a_trail(client):
    keys = {t["key"] for t in client.get("/api/trails").json()}
    pos = {p["po_number"] for p in client.get("/api/data/purchase_orders").json()}
    assert pos <= keys
    assert "vendor-V007" in keys  # the leased-line bills, which have no PO


def test_trail_lists_po_receipt_and_each_invoice_in_order(client):
    cid = client.post("/api/cases", data={"sample_id": "S02", "assigned_po": "PO-4518"}).json()["case_id"]
    _done(client, cid)
    t = client.get("/api/trails/PO-4518").json()
    kinds = [e["kind"] for e in t["events"]]
    assert kinds[:4] == ["po", "grn", "invoice", "decision"] and kinds[-1] == "waiting"
    assert t["events"][0]["doc"] == {"type": "po", "ref": "PO-4518"}
    assert t["events"][2]["doc"] == {"type": "invoice", "ref": cid} and t["money"]["ordered"] == "240000.00"


def test_needs_you_trails_come_first(client):
    trails = client.get("/api/trails").json()
    flags = [t["status"] == "needs_you" for t in trails]
    assert flags[0] and flags == sorted(flags, reverse=True)
    held = next(t for t in trails if t["key"] == "PO-4306")
    assert held["needs_you"]["case_id"] == "H-OLD-05" and "price" in held["needs_you"]["reason"].lower()


def test_split_invoices_appear_one_after_another(client):
    ev = client.get("/api/trails/PO-4540").json()["events"]
    invoices = [e["case_id"] for e in ev if e["kind"] == "invoice"]
    assert invoices == ["H-ORB-0211", "H-ORB-0214"]
    assert any(e["kind"] == "person" and e["case_id"] == "H-ORB-0214" for e in ev)


def test_running_case_shows_on_its_trail(client):
    cid = client.post("/api/cases", data={"sample_id": "S02", "assigned_po": "PO-4518", "pace": "demo"}).json()["case_id"]
    assert any(e.get("case_id") == cid for e in client.get("/api/trails/PO-4518").json()["events"])
    _done(client, cid)


def test_unknown_trail_404(client):
    assert client.get("/api/trails/PO-0000").status_code == 404

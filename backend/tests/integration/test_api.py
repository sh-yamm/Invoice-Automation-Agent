import json
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


def cached(sid):
    return (CACHE / f"{sid}_extract.json").exists() and (CACHE / f"{sid}_review.json").exists()


@pytest.fixture
def client(tmp_path):
    s = Settings()
    aop = tmp_path / "rulebook" / "aop.yaml"
    aop.parent.mkdir()
    shutil.copy(s.rulebook_path, aop)
    store = Store(tmp_path / "runs.db")
    reset_demo(store, s.seed_path)
    deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=aop,
                gateway=Gateway(s, store, CACHE, offline=True), files_dir=tmp_path / "files",
                checkpoint_path=tmp_path / "cp.db", erp_dir=s.erp_dir)
    with TestClient(create_app(deps, seed_path=s.seed_path)) as c:
        yield c


def wait_done(client, case_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        c = client.get(f"/api/cases/{case_id}").json()
        if c["status"] != "running":
            return c
        time.sleep(0.2)
    raise AssertionError("case did not finish")


def sse_events(client, case_id):
    with client.stream("GET", f"/api/cases/{case_id}/events") as r:
        body = "".join(r.iter_text())
    events = []
    for chunk in body.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in chunk.splitlines() if ": " in l)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_samples_listing(client):
    samples = client.get("/api/samples").json()
    assert len(samples) == 16 and samples[0]["id"] == "S01" and samples[0]["title"]


@pytest.mark.skipif(not cached("S01"), reason="S01 replies not recorded yet")
def test_create_sample_case_and_stream(client):
    r = client.post("/api/cases", data={"sample_id": "S01", "pace": "normal"})
    assert r.status_code == 201
    cid = r.json()["case_id"]
    case = wait_done(client, cid)
    assert case["outcome"] == 0 and case["outcome_label"] == "Approved" and case["txn_type"] == "standard_po"
    assert case["pages"] == [f"/api/cases/{cid}/pages/1.png"] and case["findings"]
    events = sse_events(client, cid)
    decision = next(d for t, d in events if t == "decision")
    assert events[-1][0] == "end"  # the server closes the stream once the case stops running
    assert decision["outcome"] == 0 and [t for t, _ in events if t != "end"][-1] in ("finalised", "node_finished")
    assert client.get(f"/api/cases/{cid}/pages/1.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/cases/{cid}/file").headers["content-type"] == "application/pdf"


@pytest.mark.skipif(not cached("S02"), reason="S02 replies not recorded yet")
def test_action_idempotent(client):
    cid = client.post("/api/cases", data={"sample_id": "S02", "pace": "normal"}).json()["case_id"]
    assert wait_done(client, cid)["status"] == "waiting"
    body = {"action": "approve_anyway", "actor": "Buyer", "note": "New rate agreed by email", "action_key": "dbl-1"}
    first = client.post(f"/api/cases/{cid}/actions", json=body)
    second = client.post(f"/api/cases/{cid}/actions", json=body)
    assert first.status_code == 200 and second.status_code in (200, 409)
    case = client.get(f"/api/cases/{cid}").json()
    assert len(case["human_actions"]) == 1 and case["outcome"] == 0
    po = next(p for p in client.get("/api/data/po_ledger").json() if p["po_number"] == "PO-4518")
    assert po["invoiced"] == "247200.00"


def test_action_on_unknown_case_404(client):
    assert client.post("/api/cases/nope/actions", json={"action": "reject"}).status_code == 404


def test_get_aop_and_put(client):
    aop = client.get("/api/aop").json()
    assert aop["tolerance"]["price"]["over_pct"] == "2.0" and "BANK_DETAILS_MISMATCH" in aop["locked"]
    r = client.put("/api/aop", json={"changes": {"tolerance.price.over_pct": "3.0"}, "editor": "Controller",
                                     "why": "steel prices rose"})
    assert r.status_code == 200 and r.json()["version"] == aop["version"] + 1
    assert client.get("/api/aop").json()["tolerance"]["price"]["over_pct"] == "3.0"


def test_put_aop_locked_422(client):
    r = client.put("/api/aop", json={"changes": {"locked": []}, "editor": "x", "why": "y"})
    assert r.status_code == 422 and "locked" in r.json()["detail"].lower()
    r = client.put("/api/aop", json={"changes": {"tolerance.nonsense": 1}, "editor": "x", "why": "y"})
    assert r.status_code == 422


def test_kpis_shape(client):
    k = client.get("/api/kpis").json()
    assert {"processed", "touchless_pct", "exceptions", "protected_inr", "avg_handling_seconds", "outcomes",
            "touchless_series"} <= set(k)
    assert k["processed"] >= 38 and 0 <= k["touchless_pct"] <= 100 and len(k["touchless_series"]) == 7


def test_cases_listing_and_filters(client):
    all_cases = client.get("/api/cases").json()
    held = client.get("/api/cases", params={"outcome": 2}).json()
    assert len(all_cases) >= 38 and held and all(c["outcome"] == 2 for c in held)
    assert all("findings" not in c for c in all_cases)  # list view stays light


def test_data_endpoints(client):
    assert len(client.get("/api/data/vendors").json()) == 8
    ledger = {p["po_number"]: p for p in client.get("/api/data/po_ledger").json()}
    assert ledger["PO-4490"]["invoiced"] == "600000.00" and ledger["PO-4490"]["remaining"] == "60000.00"
    assert client.get("/api/data/nonsense").status_code == 404


def test_reset_demo(client):
    client.post("/api/cases", files={"file": ("x.pdf", (REPO_ROOT / "samples" / "pdf" / "S01.pdf").read_bytes(),
                                              "application/pdf")})
    before = len(client.get("/api/cases").json())
    assert client.post("/api/demo/reset").status_code == 200
    assert len(client.get("/api/cases").json()) == 38 < before


def test_upload_non_pdf_400(client):
    r = client.post("/api/cases", files={"file": ("x.pdf", b"hello, not a pdf", "application/pdf")})
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    assert client.post("/api/cases", data={}).status_code == 400
    assert client.post("/api/cases", data={"sample_id": "S99"}).status_code == 404


@pytest.mark.skipif(not cached("S03"), reason="S03 replies not recorded yet")
def test_case_lists_locked_codes(client):
    cid = client.post("/api/cases", data={"sample_id": "S03", "pace": "normal"}).json()["case_id"]
    case = wait_done(client, cid)
    assert case["locked_codes"] == ["BANK_DETAILS_MISMATCH"]
    r = client.post(f"/api/cases/{cid}/actions", json={"action": "approve_anyway", "action_key": "a"})
    assert r.status_code == 422 and "note" in r.json()["detail"]


@pytest.mark.skipif(not cached("S02"), reason="S02 replies not recorded yet")
def test_case_trail_goods_po(client):
    cid = client.post("/api/cases", data={"sample_id": "S02", "pace": "normal"}).json()["case_id"]
    wait_done(client, cid)
    t = client.get(f"/api/cases/{cid}/trail").json()
    assert t["vendor"]["name"] == "Deccan Steel Traders"
    assert t["po"]["po_number"] == "PO-4518" and t["po"]["po_date"] == "2026-10-08"
    line = t["po"]["lines"][0]
    assert line["qty"] == "4000" and line["rate"] == "60.00" and line["received_qty"] == "4000"
    assert t["grns"][0]["grn_number"] == "GRN-7741" and t["grns"][0]["received_date"] == "2026-10-27"
    assert t["invoice"]["invoice_no"] == "DST/2627/0981"
    kinds = [s["kind"] for s in t["steps"]]
    assert kinds[:3] == ["po", "grn", "invoice"] and "decision" in kinds
    assert kinds.index("decision") > kinds.index("check")


@pytest.mark.skipif(not cached("S04"), reason="S04 replies not recorded yet")
def test_case_trail_recurring_contract_and_earlier_invoices(client):
    cid = client.post("/api/cases", data={"sample_id": "S04", "pace": "normal"}).json()["case_id"]
    wait_done(client, cid)
    t = client.get(f"/api/cases/{cid}/trail").json()
    assert t["po"]["po_number"] == "PO-4490" and t["contract"]["contract_id"] == "CT-901"
    assert t["grns"] == [] and len(t["earlier_invoices"]) >= 1
    assert all(e["case_id"] != cid for e in t["earlier_invoices"])
    assert "contract" in [s["kind"] for s in t["steps"]]


def test_case_trail_unknown_404(client):
    assert client.get("/api/cases/C-NOPE/trail").status_code == 404


def test_kpis_for_last_7_days(client):
    from datetime import datetime, timedelta
    week = client.get("/api/kpis?days=7").json()
    every = client.get("/api/kpis").json()
    cutoff = datetime.now() - timedelta(days=7)
    recent = [c for c in client.get("/api/cases").json()
              if c["outcome"] is not None and datetime.fromisoformat(c["created_at"]) >= cutoff]
    assert week["processed"] == len(recent) < every["processed"]
    assert week["days"] == 7 and every["days"] is None


def test_prepare_renders_pages_before_the_run(tmp_path):
    """The invoice image must be on screen the moment a case opens, not after the run finishes."""
    from ap_agent.api.common import case_json
    from ap_agent.pipeline.graph import Pipeline
    s = Settings()
    store = Store(tmp_path / "runs.db")
    deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=s.rulebook_path,
                gateway=Gateway(s, store, CACHE, offline=True), files_dir=tmp_path / "files",
                checkpoint_path=tmp_path / "cp.db", erp_dir=s.erp_dir)
    Pipeline(deps).prepare("C-PREP01", REPO_ROOT / "samples" / "pdf" / "S01.pdf", sample_id="S01")
    out = case_json(store.get_case("C-PREP01"), deps, full=True)
    assert out["pages"] == ["/api/cases/C-PREP01/pages/1.png"]


def test_page_images_are_cacheable(client):
    cid = client.post("/api/cases", data={"sample_id": "S01", "pace": "normal"}).json()["case_id"]
    r = client.get(f"/api/cases/{cid}/pages/1.png")
    assert r.status_code == 200 and "max-age" in r.headers.get("cache-control", "")


def test_normal_runs_at_full_speed_and_demo_mode_paces_the_stages(client):
    from ap_agent.api.common import AppContext  # noqa: F401
    bus = client.app.state.ctx.deps.bus
    normal = client.post("/api/cases", data={"sample_id": "S01", "pace": "normal"}).json()["case_id"]
    demo = client.post("/api/cases", data={"sample_id": "S01", "pace": "demo"}).json()["case_id"]
    default = client.post("/api/cases", data={"sample_id": "S01"}).json()["case_id"]
    assert bus.pace_by_case[normal] == 0 and bus.pace_by_case[default] == 0
    assert bus.pace_by_case[demo] > 0


def test_create_case_records_the_po_it_was_uploaded_to(client):
    cid = client.post("/api/cases", data={"sample_id": "S02", "assigned_po": "PO-4518"}).json()["case_id"]
    assert client.get(f"/api/cases/{cid}").json()["assigned_po"] == "PO-4518"

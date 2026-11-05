"""End to end: real sample PDFs through the whole LangGraph pipeline.

Model calls are served from samples/cache (recorded once with `py -3.11 samples/seed_cache.py`).
The gateway runs offline here, so a missing cache entry fails loudly instead of calling the network.
"""
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from ap_agent.ai.gateway import AiUnavailable, Gateway
from ap_agent.core.config import REPO_ROOT, Settings
from ap_agent.core.models import Outcome
from ap_agent.erp.repository import Repository
from ap_agent.pipeline.graph import ActionError, Deps, Pipeline
from ap_agent.storage.cases import Store
from ap_agent.storage.seed import reset_demo
from factories import FakeGateway
from samples.specs import SPECS

CACHE = REPO_ROOT / "samples" / "cache"
PDF = REPO_ROOT / "samples" / "pdf"
def cached(sid: str) -> bool:
    return (CACHE / f"{sid}_extract.json").exists() and (CACHE / f"{sid}_parse_p1.json").exists()


def require_cache(*sids: str) -> None:
    missing = [s for s in sids if not cached(s)]
    if missing:
        pytest.skip(f"no recorded model replies for {', '.join(missing)}: run `py -3.11 samples/seed_cache.py`")


def make_pipeline(tmp_path, gateway=None):
    s = Settings()
    store = Store(tmp_path / "runs.db")
    reset_demo(store, s.seed_path)
    gw = gateway or Gateway(s, store, CACHE, offline=True)
    deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=s.rulebook_path, gateway=gw,
                files_dir=tmp_path / "files", checkpoint_path=tmp_path / "checkpoints.db", pace_ms=0)
    return Pipeline(deps), store


@pytest.mark.parametrize("sid", sorted(SPECS))
def test_e2e_sample(sid, tmp_path):
    require_cache(sid)
    p, store = make_pipeline(tmp_path)
    case = p.start(f"e2e-{sid}", PDF / f"{sid}.pdf", sample_id=sid)
    spec = SPECS[sid]
    detail = [(f.code, f.title) for f in case["findings"] if f.status != "pass"]
    assert (case["outcome"], case["primary_code"]) == (spec.expected_outcome, spec.expected_code), detail


def test_lookalike_lists_both_reasons(tmp_path):
    require_cache("S15")
    p, _ = make_pipeline(tmp_path)
    case = p.start("e2e-S15", PDF / "S15.pdf", sample_id="S15")
    assert {"VENDOR_NOT_APPROVED", "LOOKALIKE_VENDOR"} <= {f.code for f in case["findings"]}


def test_resume_confirm_field_s08(tmp_path):
    require_cache("S08")
    p, store = make_pipeline(tmp_path)
    case = p.start("e2e-S08", PDF / "S08.pdf", sample_id="S08")
    assert case["primary_code"] == "LOW_CONFIDENCE_FIELD" and case["status"] == "waiting"
    case = p.resume("e2e-S08", {"action": "confirm_field", "field": "invoice_date", "value": "02/11/2026",
                                "actor": "AP clerk", "action_key": "k1"})
    assert case["outcome"] is Outcome.APPROVED and case["status"] == "done"
    assert store.ledger.invoiced("PO-4507", 1)[0] == 8
    assert [a["action"] for a in case["human_actions"]] == ["confirm_field"]


def test_approve_anyway_locked_requires_note(tmp_path):
    require_cache("S03")
    p, store = make_pipeline(tmp_path)
    case = p.start("e2e-S03", PDF / "S03.pdf", sample_id="S03")
    assert case["primary_code"] == "BANK_DETAILS_MISMATCH"
    with pytest.raises(ActionError, match="note"):
        p.resume("e2e-S03", {"action": "approve_anyway", "actor": "AP clerk", "action_key": "k1"})
    case = p.resume("e2e-S03", {"action": "approve_anyway", "actor": "AP clerk", "action_key": "k2",
                                "note": "Called Kaveri on the number on file; change confirmed by their CFO."})
    assert case["outcome"] is Outcome.APPROVED and case["primary_code"] == "APPROVED_BY_PERSON"
    assert store.ledger.invoiced("PO-4522", 1)[0] == 5000


def test_reject_action(tmp_path):
    require_cache("S02")
    p, store = make_pipeline(tmp_path)
    p.start("e2e-S02", PDF / "S02.pdf", sample_id="S02")
    case = p.resume("e2e-S02", {"action": "reject", "actor": "Buyer", "action_key": "k1", "note": "Rate not agreed."})
    assert case["outcome"] is Outcome.REJECTED and store.ledger.invoiced("PO-4518")[1] == 0


def test_events_order(tmp_path):
    require_cache("S01")
    p, store = make_pipeline(tmp_path)
    p.start("e2e-S01", PDF / "S01.pdf", sample_id="S01")
    events = store.get_case("e2e-S01")["events"]
    nodes = [e["payload"]["node"] for e in events if e["type"] == "node_started"]
    assert nodes[:5] == ["ingest", "render", "parse", "reconcile", "extract"]
    assert nodes.index("classify_transaction") < nodes.index("validate") < nodes.index("standard_po") \
        < nodes.index("controls") < nodes.index("decide") < nodes.index("finalise")
    assert any(e["type"] == "finding" for e in events)
    types = [e["type"] for e in events]
    assert types.index("decision") < len(types) - 1 and types[-1] == "node_finished"


def letter_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(72, 760, "Dear Sir, we are pleased to share our new product catalogue.")
    c.save()
    return path


def test_graph_non_invoice_pdf(tmp_path):
    gw = FakeGateway(json_replies=[{"fields": {"doc_title": {"value": None, "confidence": 0.9}}, "lines": []},
                                   {"doc_type": "other", "confidence": 0.95, "why": "a sales letter"}])
    gw.parse_page = lambda png, case_id=None, cache_key=None: "<x_0.1><y_0.1>Dear Sir, we are pleased<x_0.9><y_0.12><class_Text>"
    p, _ = make_pipeline(tmp_path, gateway=gw)
    case = p.start("letter", letter_pdf(tmp_path / "letter.pdf"))
    assert (case["outcome"], case["primary_code"]) == (Outcome.REJECTED, "NOT_A_TAX_INVOICE")


def test_ai_outage_holds_never_approves(tmp_path):
    gw = FakeGateway()

    def down(*a, **k):
        raise AiUnavailable("service down")
    gw.parse_page = down
    p, _ = make_pipeline(tmp_path, gateway=gw)
    case = p.start("outage", PDF / "S01.pdf")
    assert (case["outcome"], case["primary_code"]) == (Outcome.ON_HOLD, "AI_UNAVAILABLE")

"""End to end: real sample PDFs through the whole LangGraph pipeline.

Model calls are served from samples/cache (recorded once with `py -3.11 samples/seed_cache.py`).
The gateway runs offline here, so a missing cache entry fails loudly instead of calling the network.
"""
import json
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


class SmudgedDate:
    """Replays S08's recorded replies but reports the invoice date as only 71% certain, as a hard-to-read scan would."""

    def __init__(self, inner):
        self.inner, self.models = inner, inner.models

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def chat_json(self, slot, messages, schema, **kw):
        data, reasoning = self.inner.chat_json(slot, messages, schema, **kw)
        if kw.get("node") == "extract":
            data = json.loads(json.dumps(data))
            data["fields"]["invoice_date"]["confidence"] = 0.71
        return data, reasoning


def test_resume_confirm_field_s08(tmp_path):
    require_cache("S08")
    s = Settings()
    store = Store(tmp_path / "runs.db")
    reset_demo(store, s.seed_path)
    gw = SmudgedDate(Gateway(s, store, CACHE, offline=True))
    deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=s.rulebook_path, gateway=gw,
                files_dir=tmp_path / "files", checkpoint_path=tmp_path / "cp.db", pace_ms=0)
    p = Pipeline(deps)
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
    # a digital PDF is read from its parsed text by the fast text model; only scans go to the vision model
    assert gw.calls[0][:3] == ("chat_json", "extract_text", "extract")


def test_ai_outage_holds_never_approves(tmp_path):
    gw = FakeGateway()

    def down(*a, **k):
        raise AiUnavailable("service down")
    gw.parse_page = down
    p, _ = make_pipeline(tmp_path, gateway=gw)
    case = p.start("outage", PDF / "S01.pdf")
    assert (case["outcome"], case["primary_code"]) == (Outcome.ON_HOLD, "AI_UNAVAILABLE")


class FlakyExtract:
    """The model that reads the invoice's fields is down for the first call, then recovers.
    (A parser outage alone no longer holds a digital invoice: it falls back to the PDF's own text.)"""

    def __init__(self, inner):
        self.inner, self.models, self.down = inner, inner.models, True

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def chat_json(self, slot, messages, schema, **kw):
        if self.down and kw.get("node") == "extract":
            self.down = False
            raise AiUnavailable("every model failed")
        return self.inner.chat_json(slot, messages, schema, **kw)


def test_recheck_recovers_after_an_ai_outage(tmp_path):
    require_cache("S01")
    s = Settings()
    store = Store(tmp_path / "runs.db")
    reset_demo(store, s.seed_path)
    deps = Deps(repo=Repository.load(s.erp_dir), store=store, aop_path=s.rulebook_path,
                gateway=FlakyExtract(Gateway(s, store, CACHE, offline=True)), files_dir=tmp_path / "files",
                checkpoint_path=tmp_path / "cp.db", pace_ms=0)
    p = Pipeline(deps)
    case = p.start("flaky", PDF / "S01.pdf", sample_id="S01")
    assert (case["outcome"], case["primary_code"]) == (Outcome.ON_HOLD, "AI_UNAVAILABLE")
    case = p.resume("flaky", {"action": "recheck", "actor": "AP clerk", "action_key": "r1"})
    assert (case["outcome"], case["primary_code"]) == (Outcome.APPROVED, "ALL_CHECKS_PASSED")
    assert "AI_UNAVAILABLE" not in {f.code for f in case["findings"]}


def test_a_crash_outside_the_nodes_never_leaves_a_case_running(tmp_path, monkeypatch):
    p, store = make_pipeline(tmp_path, gateway=FakeGateway())

    def boom(*a, **k):
        raise RuntimeError("graph exploded")
    monkeypatch.setattr(p.app, "invoke", boom)
    case = p.start("crash", PDF / "S01.pdf")
    assert case["status"] == "waiting" and case["outcome"] is Outcome.ON_HOLD and case["primary_code"] == "TOOL_ERROR"


class _ParserDown(Gateway):
    """Recorded replies for everything except the page parser, which is unreachable."""

    def parse_page(self, png, *, case_id=None, cache_key=None):
        raise AiUnavailable("parser down")


def test_digital_invoice_is_read_from_its_own_text_when_the_page_parser_is_down(tmp_path):
    require_cache("S01")
    s = Settings()
    p, store = make_pipeline(tmp_path)
    p.deps.gateway = _ParserDown(s, store, CACHE, offline=True)
    p = Pipeline(p.deps)
    case = p.start("C-PD1", REPO_ROOT / "samples" / "pdf" / "S01.pdf", sample_id="S01")
    assert case["outcome"] is Outcome.APPROVED
    parse = next(f for f in case["findings"] if f.check == "parse_pages")
    assert parse.status.value == "warn" and "text" in parse.title.lower()


def test_scan_still_holds_when_the_page_parser_is_down(tmp_path):
    require_cache("S08")
    s = Settings()
    p, store = make_pipeline(tmp_path)
    p.deps.gateway = _ParserDown(s, store, CACHE, offline=True)
    p = Pipeline(p.deps)
    case = p.start("C-PD2", REPO_ROOT / "samples" / "pdf" / "S08.pdf", sample_id="S08")
    assert case["outcome"] is Outcome.ON_HOLD and case["primary_code"] == "AI_UNAVAILABLE"


def test_invoice_without_a_po_number_uses_the_po_it_was_uploaded_to(tmp_path):
    require_cache("S08")
    p, _ = make_pipeline(tmp_path)
    case = p.start("C-AS1", PDF / "S08.pdf", sample_id="S08", assigned_po="PO-4507")
    checks = {f.check: f for f in case["findings"]}
    assert "PO_INFERRED" not in {f.code for f in case["findings"]}
    assert checks["po_assignment"].status.value == "pass" and "PO-4507" in checks["po_assignment"].title
    assert checks["po_resolve"].status.value == "pass" and checks["po_resolve"].data["po"] == "PO-4507"


def test_invoice_naming_another_po_is_held_and_can_be_assigned_to_the_right_one(tmp_path):
    require_cache("S01")
    p, store = make_pipeline(tmp_path)
    case = p.start("C-AS2", PDF / "S01.pdf", sample_id="S01", assigned_po="PO-4518")
    assert case["outcome"] is Outcome.ON_HOLD
    assert "PO_ASSIGNMENT_MISMATCH" in {f.code for f in case["findings"]}
    case = p.resume("C-AS2", {"action": "confirm_field", "field": "po_ref", "value": "PO-4501",
                              "actor": "AP clerk", "action_key": "as1"})
    assert case["outcome"] is Outcome.APPROVED
    assert "PO_ASSIGNMENT_MISMATCH" not in {f.code for f in case["findings"]}
    assert store.get_case("C-AS2")["assigned_po"] == "PO-4501"


def test_a_persons_decision_names_the_reason_in_words_not_its_code(tmp_path):
    require_cache("S03")
    p, store = make_pipeline(tmp_path)
    p.start("e2e-S03w", PDF / "S03.pdf", sample_id="S03")
    case = p.resume("e2e-S03w", {"action": "approve_anyway", "actor": "AP clerk", "action_key": "k1",
                                 "note": "Called the vendor on the number on file."})
    assert "BANK_DETAILS_MISMATCH" not in case["why"]
    assert "Bank account differs from the vendor record" in case["why"]


def test_rates_printed_with_gst_are_converted_then_matched(tmp_path):
    require_cache("S17")
    p, store = make_pipeline(tmp_path)
    case = p.start("e2e-S17", PDF / "S17.pdf", sample_id="S17")
    codes = {f.code for f in case["findings"]}
    assert case["outcome"] is Outcome.APPROVED and "TAX_INCLUSIVE_NORMALISED" in codes
    assert "PRICE_VARIANCE" not in codes and "ARITHMETIC_MISMATCH" not in codes
    assert json.loads(store.get_case("e2e-S17")["invoice_json"])["lines"][0]["rate"] in ("3500.00", "3500")


def test_the_reviewing_agent_holds_a_clean_invoice_that_presses_for_payment(tmp_path):
    """S18 passes every rule; only the agent, reading the invoice text, puts it on hold."""
    require_cache("S18")
    p, store = make_pipeline(tmp_path)
    case = p.start("e2e-S18", PDF / "S18.pdf", sample_id="S18")
    assert case["outcome"] is Outcome.ON_HOLD and case["primary_code"] == "AGENT_ESCALATION"
    rule_fails = [f.code for f in case["findings"] if f.status.value == "fail" and f.check != "agent_review"]
    assert rule_fails == []
    esc = next(f for f in case["findings"] if f.code == "AGENT_ESCALATION")
    assert "ctx:invoice_text" in esc.data["cites"]
    review = [l for l in store.get_case("e2e-S18")["llm_calls"] if l["node"] == "agent_review"]
    assert review and len(review[-1]["reasoning"] or "") > 200


# ---------- trial runs: demo invoices can be run again and again ----------

def test_a_demo_invoice_run_twice_gets_the_same_result(tmp_path):
    """A trial run never counts as history: not the same file, not a past invoice, not billed on the PO."""
    require_cache("S01")
    p, store = make_pipeline(tmp_path)
    first = p.start("trial-1", PDF / "S01.pdf", sample_id="S01", trial=True)
    second = p.start("trial-2", PDF / "S01.pdf", sample_id="S01", trial=True)
    assert first["outcome"] is Outcome.APPROVED and second["outcome"] is Outcome.APPROVED
    assert second["primary_code"] == "ALL_CHECKS_PASSED"
    assert store.ledger.invoiced("PO-4501")[1] == 0  # the trial approvals didn't use up the PO


def test_a_real_invoice_still_counts_as_history(tmp_path):
    require_cache("S01")
    p, store = make_pipeline(tmp_path)
    p.start("real-1", PDF / "S01.pdf", sample_id="S01")
    again = p.start("real-2", PDF / "S01.pdf", sample_id="S01")
    assert again["primary_code"] == "DUPLICATE_EXACT"
    assert store.ledger.invoiced("PO-4501")[1] > 0

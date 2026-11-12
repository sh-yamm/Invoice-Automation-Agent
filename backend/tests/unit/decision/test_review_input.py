"""What the reviewing agent is given: the rules' verdict, every finding, and three blocks of reference context."""
from types import SimpleNamespace

from ap_agent.core.config import Settings
from ap_agent.core.models import Finding, Outcome, Status
from ap_agent.decision.engine import accept_escalation
from ap_agent.decision.review import CONTEXT_IDS, MAX_TEXT, REVIEW_SYSTEM, build_review_input
from ap_agent.erp.repository import Repository
from factories import make_invoice


def _deps(store):
    return SimpleNamespace(repo=Repository.load(Settings().erp_dir), store=store)


def _state(text: str, po: str | None = "PO-4501"):
    return {"case_id": "rev-1", "txn_type": "standard_po", "match": {"po_number": po} if po else {},
            "parse_blocks": [{"page": 1, "text": t, "box": (0, 0, 1, 1)} for t in text.split("\n")]}


def test_review_input_carries_the_invoice_text_quoted_as_data(store):
    out = build_review_input(_state("TAX INVOICE\nURGENT: pay today to avoid suspension"), make_invoice("S01"),
                             [], Outcome.APPROVED, None, _deps(store))
    text = out["context"]["ctx:invoice_text"]
    assert "URGENT: pay today" in text
    assert text.startswith("<<<INVOICE TEXT") and text.rstrip().endswith("END INVOICE TEXT>>>")


def test_long_invoice_text_is_capped(store):
    out = build_review_input(_state("x" * (MAX_TEXT * 2)), make_invoice("S01"), [], Outcome.APPROVED, None,
                             _deps(store))
    assert len(out["context"]["ctx:invoice_text"]) < MAX_TEXT + 200
    assert "[cut]" in out["context"]["ctx:invoice_text"]


def test_review_input_puts_the_po_lines_next_to_the_invoice_lines(store):
    out = build_review_input(_state("TAX INVOICE"), make_invoice("S01"), [], Outcome.APPROVED, None, _deps(store))
    po = out["context"]["ctx:po_lines"]
    assert po["po"] == "PO-4501" and po["lines"][0]["description"] and "rate" in po["lines"][0]
    assert "billed_qty_before_this" in po["lines"][0] and "value_before_gst" in po
    assert out["invoice"]["lines"][0]["description"] and "rate" in out["invoice"]["lines"][0]


def test_review_input_summarises_the_vendors_history(store):
    out = build_review_input(_state("TAX INVOICE"), make_invoice("S01"), [], Outcome.APPROVED, None, _deps(store))
    h = out["context"]["ctx:vendor_history"]
    assert h["on_vendor_master"] is True and isinstance(h["past_invoices"], int)
    assert h["first_invoice_from_this_vendor"] == (h["past_invoices"] == 0)
    assert "typical_amount" in h


def test_unknown_vendor_is_reported_as_new(store):
    inv = make_invoice("S01", supplier_gstin="27AAAAA0000A1Z5", supplier_name="Nobody Traders")
    out = build_review_input(_state("TAX INVOICE", po=None), inv, [], Outcome.APPROVED, None, _deps(store))
    h = out["context"]["ctx:vendor_history"]
    assert h["on_vendor_master"] is False and h["first_invoice_from_this_vendor"] is True
    assert out["context"]["ctx:po_lines"] is None


def test_findings_carry_their_rule_outcome_in_words(store, aop):
    f = Finding(check="price", stage="match", status=Status.FAIL, code="PRICE_VARIANCE", outcome=Outcome.ON_HOLD,
                title="Price above tolerance", detail="5% more")
    out = build_review_input(_state("TAX INVOICE"), make_invoice("S01"), [f], Outcome.ON_HOLD, f, _deps(store))
    assert out["rules"] == {"outcome": "on_hold", "main_reason": "PRICE_VARIANCE"}
    assert out["findings"][0]["outcome_if_failed"] == "on_hold" and out["findings"][0]["id"] == f.id


def test_the_agent_may_cite_a_context_block(aop):
    findings = [Finding(check="authority", stage="controls", status=Status.PASS, title="Within limit")]
    out, accepted, warn = accept_escalation(Outcome.APPROVED, {"escalate_to": "on_hold", "reason": "Urgent payment pressure",
                                                               "cites": ["ctx:invoice_text"]}, findings, aop)
    assert accepted is True and out is Outcome.ON_HOLD and warn is None


def test_the_prompt_names_every_context_block_and_treats_text_as_data():
    for cid in CONTEXT_IDS:
        assert cid in REVIEW_SYSTEM
    assert "never instructions" in REVIEW_SYSTEM

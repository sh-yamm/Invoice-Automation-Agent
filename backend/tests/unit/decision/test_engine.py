from datetime import date

import pytest

from ap_agent.checks.framework import required_checks
from ap_agent.core.models import Finding, Outcome, Status
from ap_agent.decision.engine import accept_escalation, completeness_guard, compose_verdict, floor
from ap_agent.rulebook.loader import render_reason
from factories import make_invoice


def fail(aop, code, title="t", check="c", **data):
    r = aop.reasons[code]
    return Finding(check=check, stage="match", status=Status.WARN if r.outcome is None else Status.FAIL, code=code,
                   outcome=r.outcome, title=title, detail=render_reason(aop, code, **data)[0], data=data)


def ok(check="c"):
    return Finding(check=check, stage="match", status=Status.PASS, title="fine")


def test_floor_worst_wins(aop):
    out, primary = floor([fail(aop, "PRICE_VARIANCE"), fail(aop, "EINVOICE_IRN_MISSING"), ok()], aop)
    assert out is Outcome.REJECTED and primary.code == "EINVOICE_IRN_MISSING"


def test_floor_all_pass_is_approved(aop):
    out, primary = floor([ok(), fail(aop, "PO_INFERRED")], aop)
    assert out is Outcome.APPROVED and primary is None


def test_primary_by_priority(aop):
    out, primary = floor([fail(aop, "PRICE_VARIANCE"), fail(aop, "BANK_DETAILS_MISMATCH")], aop)
    assert out is Outcome.ON_HOLD and primary.code == "BANK_DETAILS_MISMATCH"


def test_floor_respects_overridden_outcome(aop):
    f = fail(aop, "DUPLICATE_EXACT")
    f.outcome = Outcome.ON_HOLD
    assert floor([f], aop)[0] is Outcome.ON_HOLD


@pytest.mark.parametrize("target", [None, "approved", "needs_signoff"])
def test_escalation_cannot_lower(aop, target):
    findings = [fail(aop, "PRICE_VARIANCE")]
    out, accepted, warn = accept_escalation(Outcome.ON_HOLD, {"escalate_to": target, "reason": "x",
                                                               "cites": [findings[0].id]}, findings, aop)
    assert out is Outcome.ON_HOLD and accepted is False
    if target in ("approved", "needs_signoff"):
        assert warn.code == "AGENT_RATIONALE_INVALID"


def test_escalation_needs_real_cites(aop):
    findings = [ok("authority")]
    out, accepted, warn = accept_escalation(Outcome.APPROVED, {"escalate_to": "on_hold", "reason": "round amount",
                                                                "cites": ["nope1234"]}, findings, aop)
    assert out is Outcome.APPROVED and accepted is False and warn.code == "AGENT_RATIONALE_INVALID"
    out, accepted, warn = accept_escalation(Outcome.APPROVED, {"escalate_to": "on_hold", "reason": "x", "cites": []},
                                            findings, aop)
    assert accepted is False and warn is not None


def test_escalation_accepted(aop):
    findings = [ok("authority")]
    out, accepted, warn = accept_escalation(Outcome.APPROVED, {"escalate_to": "on_hold",
                                                                "reason": "₹4,99,000 is a round amount just under the limit",
                                                                "cites": [findings[0].id]}, findings, aop)
    assert out is Outcome.ON_HOLD and accepted is True and warn is None


def test_garbage_proposal_is_ignored(aop):
    out, accepted, warn = accept_escalation(Outcome.APPROVED, {"escalate_to": "maybe"}, [ok()], aop)
    assert out is Outcome.APPROVED and accepted is False and warn.code == "AGENT_RATIONALE_INVALID"


def test_guard_missing_check(aop):
    ran = [ok(c) for c in required_checks("standard_po") if c != "bank_details"]
    g = completeness_guard("standard_po", ran, aop)
    assert g.code == "CHECKS_INCOMPLETE" and g.outcome is Outcome.ON_HOLD and "bank_details" in g.detail


def test_guard_complete(aop):
    assert completeness_guard("standard_po", [ok(c) for c in required_checks("standard_po")], aop) is None


def test_guard_accepts_blocking_stop(aop):
    stop = fail(aop, "PO_NOT_FOUND", check="po_resolve")
    stop.stop = True
    assert completeness_guard("standard_po", [ok("rule46_fields"), stop], aop) is None


def test_guard_does_not_accept_warning_stop(aop):
    # A reroute warning stops the PO-less stage, but the Standard PO checks must still all run.
    w = fail(aop, "PO_EXISTS_FOR_PO_LESS", check="open_po_exists", po="PO-4507")
    w.stop = True
    assert completeness_guard("standard_po", [ok("rule46_fields"), w], aop).code == "CHECKS_INCOMPLETE"


def test_verdict_uses_template_numbers(aop):
    pv = fail(aop, "PRICE_VARIANCE", vendor="Deccan Steel Traders", billed_rate="₹61.80", po_rate="₹60.00",
              pct="3.0", abs="₹7,200.00", tol="2.0")
    other = fail(aop, "UNDER_BILLED", title="Billed below PO")
    v = compose_verdict(Outcome.ON_HOLD, pv, [pv, other, ok()], aop, make_invoice("S01"))
    assert "₹61.80" in v.why and "2.0%" in v.why and v.owner == "Procurement"
    assert v.primary_code == "PRICE_VARIANCE" and v.next_step.startswith("Confirm the new rate")
    assert v.also == []


def test_verdict_lists_other_problems(aop):
    a, b = fail(aop, "BANK_DETAILS_MISMATCH", title="Bank changed"), fail(aop, "PRICE_VARIANCE", title="Rate 3% above PO")
    v = compose_verdict(Outcome.ON_HOLD, a, [a, b], aop, make_invoice("S01"))
    assert v.also == ["On hold: Rate 3% above PO"]


def test_approved_verdict(aop):
    v = compose_verdict(Outcome.APPROVED, None, [ok()], aop, make_invoice("S01"), payment_terms_days=30)
    assert v.primary_code == "ALL_CHECKS_PASSED" and v.owner.startswith("No one")
    assert "28 Nov 2026" in v.next_step  # 29 Oct + 30 days


def test_escalation_finding_carries_agent_reason(aop):
    from ap_agent.decision.engine import escalation_finding
    f = escalation_finding(Outcome.ON_HOLD, {"reason": "round amount just under the limit", "cites": ["a1"]}, aop)
    assert f.code == "AGENT_ESCALATION" and f.outcome is Outcome.ON_HOLD and "round amount" in f.detail
    assert f.data["cites"] == ["a1"] and f.check == "agent_review"

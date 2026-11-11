"""Stage 6: the decision. Rules set the floor; the agent may only make it stricter; the verdict text
comes from the rulebook, never from the model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ap_agent.checks.framework import required_checks
from ap_agent.core.constants import OUTCOME_LABELS
from ap_agent.core.models import Finding, Invoice, Outcome, Status
from ap_agent.rulebook.loader import Aop, render_reason

_TARGETS = {"approved": Outcome.APPROVED, "needs_signoff": Outcome.NEEDS_SIGNOFF,
            "on_hold": Outcome.ON_HOLD, "rejected": Outcome.REJECTED}
_BLOCKING = {Outcome.ON_HOLD, Outcome.REJECTED}


@dataclass
class Verdict:
    outcome: Outcome
    primary_code: str
    why: str
    owner: str
    next_step: str
    also: list[str] = field(default_factory=list)


def _finding(aop: Aop, code: str, title: str, check: str, data: dict, outcome: Outcome | None = None) -> Finding:
    reason = aop.reasons[code]
    out = outcome if outcome is not None else reason.outcome
    return Finding(check=check, stage="decide", status=Status.WARN if out is None else Status.FAIL, code=code,
                   outcome=out, title=title, detail=render_reason(aop, code, **data)[0], data=data)


def completeness_guard(path: str | None, findings: list[Finding], aop: Aop) -> Finding | None:
    """Refuse to decide if a required check for this path left no trace.

    A blocking stop (a hold or reject that ended a stage early) is complete by definition: the case
    cannot be approved anyway. A warning stop (a reroute) is not: the new path's checks must all run.
    """
    if any(f.stop and f.outcome in _BLOCKING for f in findings):
        return None
    ran = {f.check for f in findings}
    missing = [c for c in required_checks(path) if c not in ran] if path else []
    if missing:
        return _finding(aop, "CHECKS_INCOMPLETE", "Required checks did not run", "completeness_guard",
                        {"missing": ", ".join(missing)})
    return None


def floor(findings: list[Finding], aop: Aop) -> tuple[Outcome, Finding | None]:
    """The rule-based outcome: the most severe finding wins; ties go to the rulebook's order."""
    blocking = [f for f in findings if f.status is Status.FAIL and f.outcome is not None]
    if not blocking:
        return Outcome.APPROVED, None
    worst = max(f.outcome for f in blocking)
    primary = min((f for f in blocking if f.outcome == worst),
                  key=lambda f: aop.reasons[f.code].priority if f.code in aop.reasons else 10_000)
    return worst, primary


def accept_escalation(floor_outcome: Outcome, proposal: dict, findings: list[Finding],
                      aop: Aop) -> tuple[Outcome, bool, Finding | None]:
    """Apply the agent's review only on an invoice the rules would approve, if it is stricter and cites real findings.

    The agent catches what the rules missed. It never turns a hold or a sign-off into a rejection by restating a
    concern the rules already raised: a person decides those, with the agent's note in front of them.
    """
    target_name = (proposal or {}).get("escalate_to")
    if target_name in (None, "", "none"):
        return floor_outcome, False, None
    target = _TARGETS.get(str(target_name).lower())
    invalid = None
    if target is None:
        invalid = f"it proposed an unknown outcome ({target_name})"
    elif target < floor_outcome:
        invalid = f"it proposed {OUTCOME_LABELS[int(target)].lower()}, which is less strict than the rules"
    elif target == floor_outcome or floor_outcome > Outcome.APPROVED:
        # A person already reviews this invoice; the agent's concern reaches them as its review note
        return floor_outcome, False, None
    else:
        ids = {f.id for f in findings}
        cites = proposal.get("cites") or []
        if not cites:
            invalid = "it cited no findings"
        elif not set(cites) <= ids:
            invalid = f"it cited findings that do not exist ({', '.join(sorted(set(cites) - ids))})"
    if invalid:
        return floor_outcome, False, _finding(aop, "AGENT_RATIONALE_INVALID", "Agent review discarded",
                                              "agent_review", {"reason": invalid})
    return target, True, None


def escalation_finding(outcome: Outcome, proposal: dict, aop: Aop) -> Finding:
    return _finding(aop, "AGENT_ESCALATION", "Agent escalated on review", "agent_review",
                    {"reason": proposal.get("reason", ""), "cites": list(proposal.get("cites") or [])},
                    outcome=outcome)


def compose_verdict(outcome: Outcome, primary: Finding | None, findings: list[Finding], aop: Aop,
                    invoice: Invoice, payment_terms_days: int = 30) -> Verdict:
    if primary is None:
        pay = (invoice.invoice_date + timedelta(days=payment_terms_days)).strftime("%d %b %Y") \
            if invoice.invoice_date else "the next payment run"
        why, nxt = render_reason(aop, "ALL_CHECKS_PASSED", pay_date=pay)
        return Verdict(outcome, "ALL_CHECKS_PASSED", why, aop.reasons["ALL_CHECKS_PASSED"].owner, nxt)
    reason = aop.reasons[primary.code]
    _, nxt = render_reason(aop, primary.code, **primary.data)
    others = sorted((f for f in findings if f is not primary and f.status is Status.FAIL and f.outcome is not None),
                    key=lambda f: (-int(f.outcome), aop.reasons[f.code].priority if f.code in aop.reasons else 10_000))
    also = [f"{OUTCOME_LABELS[int(f.outcome)]}: {f.title}" for f in others]
    return Verdict(outcome, primary.code, primary.detail, reason.owner, nxt, also)

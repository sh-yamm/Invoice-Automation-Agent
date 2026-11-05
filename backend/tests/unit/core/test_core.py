from decimal import Decimal

from ap_agent.core.config import Settings
from ap_agent.core.models import Finding, Outcome, Status
from ap_agent.core.money import fmt_inr, to_money


def test_outcome_order():
    assert max([Outcome.ON_HOLD, Outcome.REJECTED, Outcome.APPROVED]) is Outcome.REJECTED


def test_fmt_inr_indian_grouping():
    assert fmt_inr(Decimal("12900000.5")) == "₹1,29,00,000.50"


def test_fmt_inr_small_and_negative():
    assert fmt_inr(Decimal("999")) == "₹999.00"
    assert fmt_inr(Decimal("-58275")) == "-₹58,275.00"


def test_to_money_half_up():
    assert to_money("2.005") == Decimal("2.01")


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RPM", "7")
    assert Settings().llm_max_rpm == 7


def test_finding_defaults():
    f = Finding(check="x", stage="validate", status="pass", title="ok")
    assert len(f.id) == 8 and f.stop is False and f.status is Status.PASS

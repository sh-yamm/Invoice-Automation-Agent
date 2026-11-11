import re
import shutil
from decimal import Decimal

import pytest

from ap_agent.core.models import Outcome
from ap_agent.rulebook.loader import LockedRuleError, load_aop, render_reason, save_aop


def readme_codes(repo_root) -> set[str]:
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    section = text.split("## Outcomes and reason codes", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"`([A-Z][A-Z0-9_]+)`", section))


@pytest.fixture
def aop_copy(tmp_path, repo_root):
    p = tmp_path / "rulebook" / "aop.yaml"
    p.parent.mkdir()
    shutil.copy(repo_root / "rulebook" / "aop.yaml", p)
    return p


def test_values_verbatim(aop):
    assert aop.authority.auto_approve_limit_inr == Decimal("500000")
    assert aop.authority.po_less_auto_limit_inr == Decimal("25000")
    assert aop.authority.split_window_days == 7
    assert aop.tolerance.price.over_pct == Decimal("2.0")
    assert aop.tolerance.price.over_abs_inr == Decimal("5000")
    assert aop.duplicates.window_days == 30 and aop.duplicates.min_similarity_pct == 90
    assert aop.confidence.min_field == 0.85 and aop.confidence.po_inference_min == 0.90
    assert aop.confidence.classification_min == 0.80 and aop.confidence.gl_coding_min == 0.80
    assert aop.po_less_allowed_categories == ["utilities", "telecom", "rent", "statutory", "travel", "subscriptions"]
    assert aop.locked == {"BANK_DETAILS_MISMATCH", "VENDOR_NOT_APPROVED", "PO_VENDOR_MISMATCH",
                          "EINVOICE_IRN_MISSING", "SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT"}


def test_every_readme_code_has_reason(aop, repo_root):
    codes = readme_codes(repo_root)
    assert len(codes) > 60
    assert codes <= set(aop.reasons), sorted(codes - set(aop.reasons))
    assert aop.reasons["ALL_CHECKS_PASSED"].outcome is Outcome.APPROVED


def test_outcomes_mapped(aop):
    assert aop.reasons["EINVOICE_IRN_MISSING"].outcome is Outcome.REJECTED
    assert aop.reasons["PRICE_VARIANCE"].outcome is Outcome.ON_HOLD
    assert aop.reasons["SPLIT_BELOW_LIMIT"].outcome is Outcome.NEEDS_SIGNOFF
    assert aop.reasons["PO_INFERRED"].outcome is None


def test_render_reason(aop):
    e, n = render_reason(aop, "PRICE_VARIANCE", vendor="Deccan Steel", billed_rate="₹61.80",
                         po_rate="₹60.00", pct="3.0", abs="₹7,200", tol="2.0")
    assert "₹61.80" in e and "{" not in e and n


def test_render_reason_missing_value_does_not_crash(aop):
    e, _ = render_reason(aop, "PRICE_VARIANCE", vendor="Deccan Steel")
    assert "Deccan Steel" in e


def test_save_bumps_version(aop_copy):
    a = load_aop(aop_copy)
    changed = a.model_copy(deep=True)
    changed.tolerance.price.over_pct = Decimal("3.0")
    a2 = save_aop(changed, aop_copy, "demo", "test")
    assert a2.version == a.version + 1
    assert load_aop(aop_copy).tolerance.price.over_pct == Decimal("3.0")
    assert (aop_copy.parent / "versions" / f"v{a.version}.yaml").exists()
    text = aop_copy.read_text(encoding="utf-8")
    assert "over_pct: 3.0" in text and "# within only if BOTH hold" in text
    assert load_aop(aop_copy).last_edit["editor"] == "demo"


def test_locked_cannot_change(aop_copy):
    a = load_aop(aop_copy)
    changed = a.model_copy(deep=True)
    changed.locked = a.locked - {"BANK_DETAILS_MISMATCH"}
    with pytest.raises(LockedRuleError):
        save_aop(changed, aop_copy, "demo", "test")


def test_locked_reason_outcome_cannot_change(aop_copy):
    a = load_aop(aop_copy)
    changed = a.model_copy(deep=True)
    changed.reasons["BANK_DETAILS_MISMATCH"].outcome = Outcome.APPROVED
    with pytest.raises(LockedRuleError):
        save_aop(changed, aop_copy, "demo", "test")


def test_priority_order(aop):
    r = aop.reasons
    assert r["SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT"].priority < r["PRICE_VARIANCE"].priority
    assert r["NOT_A_TAX_INVOICE"].priority < r["VENDOR_NOT_APPROVED"].priority < r["MISSING_MANDATORY_FIELD"].priority
    assert r["SPLIT_BELOW_LIMIT"].priority < r["NEEDS_SIGNOFF"].priority


def test_period_already_billed_outranks_probable_duplicate(aop):
    assert aop.reasons["PERIOD_ALREADY_BILLED"].priority < aop.reasons["DUPLICATE_PROBABLE"].priority


def test_every_reason_has_a_plain_title():
    """The app shows a reason's plain name, never its code."""
    from ap_agent.core.config import Settings
    aop = load_aop(Settings().rulebook_path)
    missing = [c for c, r in aop.reasons.items() if not r.title or "_" in r.title]
    assert missing == []
    assert aop.reasons["PRICE_VARIANCE"].title == "Price above the agreed PO rate"

from datetime import date
from decimal import Decimal

import pytest

from ap_agent.core.config import Settings
from ap_agent.core.models import Finding, Outcome
from ap_agent.storage.cases import Store
from ap_agent.storage.seed import reset_demo, seed_history


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "runs.db")
    seed_history(s, Settings().seed_path)
    return s


def test_ledger_write_idempotent(store):
    store.create_case("c1", "S01.pdf", "abc", "S01")
    store.ledger_write("c1", "PO-4501", 1, Decimal("20"), Decimal("129000"))
    store.ledger_write("c1", "PO-4501", 1, Decimal("20"), Decimal("129000"))
    assert store.ledger.invoiced("PO-4501", 1) == (Decimal("20"), Decimal("129000"))


def test_ledger_po_total_and_seed(store):
    qty, amount = store.ledger.invoiced("PO-4490")
    assert amount == Decimal("600000")
    assert store.ledger.invoiced("PO-4540") == (Decimal("2"), Decimal("830000"))
    assert store.ledger.invoiced("PO-4501", 1) == (Decimal("0"), Decimal("0"))


def test_period_billed_after_seed(store):
    assert store.ledger.period_billed("CT-901", date(2026, 10, 1)) is not None
    assert store.ledger.period_billed("CT-901", date(2026, 11, 1)) is None


def test_history_excludes_case(store):
    store.create_case("c2", "x.pdf", "h2", None)
    store.set_invoice_summary("c2", vendor_id="V006", vendor_name="Sai Krishna Logistics",
                              invoice_no="SKL/1048", invoice_no_norm="SKL1048",
                              invoice_date=date(2026, 10, 26), grand_total=Decimal("58275"),
                              line_texts=["Freight"], period_start=None)
    hist = store.history.cases_for_vendor("V006", exclude_case="c2")
    assert "c2" not in {h.case_id for h in hist}
    original = next(h for h in hist if h.case_id == "H-SKL-1043")
    assert original.outcome is Outcome.APPROVED and original.grand_total == Decimal("58275")
    assert {h.case_id for h in store.history.cases_for_vendor("V006", exclude_case="none")} >= {"c2"}


def test_human_action_dedupe(store):
    store.create_case("c3", "x.pdf", "h3", None)
    assert store.add_human_action("c3", "approve_anyway", "demo", "checked", {}, action_key="k1") is True
    assert store.add_human_action("c3", "approve_anyway", "demo", "checked", {}, action_key="k1") is False
    assert len(store.get_case("c3")["human_actions"]) == 1


def test_case_record_roundtrip(store):
    store.create_case("c4", "S02.pdf", "h4", "S02")
    f = Finding(check="price", stage="match", status="fail", code="PRICE_VARIANCE",
                outcome=Outcome.ON_HOLD, title="Rate 3% above PO", data={"variance_pct": 3.0})
    store.add_finding("c4", f)
    store.add_event("c4", "finding", {"id": f.id})
    store.add_tool_call("c4", "classify_transaction", "vendor_lookup", {"gstin": "x"}, {"found": True})
    store.add_llm_call("c4", "extract", "m", [{"role": "user"}], {"a": 1}, "thinking", 120, 50)
    store.set_outcome("c4", Outcome.ON_HOLD, "PRICE_VARIANCE", "why", "Procurement", "next",
                      "agent note", "standard_po", "tax_invoice")
    c = store.get_case("c4")
    assert c["outcome"] is Outcome.ON_HOLD and c["primary_code"] == "PRICE_VARIANCE"
    assert c["findings"][0].code == "PRICE_VARIANCE" and c["findings"][0].data["variance_pct"] == 3.0
    assert c["events"][0]["type"] == "finding" and c["tool_calls"][0]["tool"] == "vendor_lookup"
    assert c["llm_calls"][0]["reasoning"] == "thinking"
    assert any(x["case_id"] == "c4" for x in store.list_cases({"outcome": Outcome.ON_HOLD}))


def test_case_by_sha(store):
    store.create_case("c5", "a.pdf", "same-hash", None)
    assert store.case_by_sha("same-hash", exclude_case="other") == "c5"
    assert store.case_by_sha("same-hash", exclude_case="c5") is None


def test_reset_demo_restores_seed(store):
    store.create_case("c6", "x.pdf", "h6", None)
    store.ledger_write("c6", "PO-4490", 1, Decimal("0"), Decimal("60000"))
    reset_demo(store, Settings().seed_path)
    assert store.get_case("c6") is None
    assert store.ledger.invoiced("PO-4490")[1] == Decimal("600000")
    assert len(store.list_cases({})) >= 35


def test_seeded_retainers_carry_their_billing_period(store):
    hist = {h.case_id: h for h in store.history.cases_for_vendor("V003", exclude_case="none")}
    assert hist["H-NIT-10"].period_start == date(2026, 10, 1)

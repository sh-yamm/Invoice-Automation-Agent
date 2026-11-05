"""Stage 4b: Recurring. A retainer or contract invoice: right period, right amount, not billed twice."""
from __future__ import annotations

from decimal import Decimal

from ap_agent.checks.framework import CheckContext, check
from ap_agent.checks.standard_po import balance_findings
from ap_agent.core.money import fmt_inr

STAGE = "match"
PATH = {"recurring"}


def _period(d) -> str:
    return d.strftime("%B %Y")


def _contract(ctx):
    return ctx.scratch.get("contract")


@check("contract_resolve", STAGE, PATH, "Contract found")
def contract_resolve(ctx: CheckContext):
    v = ctx.vendor
    contract = ctx.repo.contract_for(v.vendor_id, ctx.invoice.po_ref) if v else None
    if not contract:
        return [ctx.fail("CONTRACT_NOT_FOUND", "No contract for this recurring invoice", stop=True,
                         data={"vendor": v.name if v else ctx.invoice.supplier_name})]
    ctx.scratch["contract"] = contract
    ctx.po = ctx.repo.po(contract.po_number or ctx.invoice.po_ref)
    return [ctx.ok(f"Contract {contract.contract_id} found",
                   f"{contract.description}: {fmt_inr(contract.amount_per_period)} {contract.billing_cycle}",
                   data={"contract": contract.contract_id, "po": contract.po_number})]


@check("period_present", STAGE, PATH, "Billing period printed")
def period_present(ctx: CheckContext):
    if ctx.invoice.period_start is None:
        return [ctx.fail("LOW_CONFIDENCE_FIELD", "Billing period not found on the invoice",
                         evidence=ctx.ev("period_start"), data={"fields": "the billing period", "confidence": "not printed"})]
    return [ctx.ok(f"Billing period: {_period(ctx.invoice.period_start)}")]


@check("contract_active", STAGE, PATH, "Period inside the contract dates")
def contract_active(ctx: CheckContext):
    c, p = _contract(ctx), ctx.invoice.period_start
    if not c or not p:
        return [ctx.ok("Not checked: no billing period")]
    if not (c.start_date <= p <= c.end_date):
        return [ctx.fail("CONTRACT_NOT_ACTIVE", "Billing period outside the contract", evidence=ctx.ev("period_start"),
                         data={"period": _period(p), "contract": c.contract_id,
                               "start": c.start_date.strftime("%d %b %Y"), "end": c.end_date.strftime("%d %b %Y")})]
    return []


@check("period_not_billed", STAGE, PATH, "Period not already billed")
def period_not_billed(ctx: CheckContext):
    c, p = _contract(ctx), ctx.invoice.period_start
    if not c or not p:
        return [ctx.ok("Not checked: no billing period")]
    other = ctx.ledger.period_billed(c.contract_id, p, exclude_case=ctx.case_id)
    if other:
        prev = next((h for h in ctx.history.cases_for_vendor(c.vendor_id, exclude_case=ctx.case_id)
                     if h.case_id == other), None)
        return [ctx.fail("PERIOD_ALREADY_BILLED", f"{_period(p)} was already billed", evidence=ctx.ev("period_start"),
                         data={"period": _period(p), "contract": c.contract_id, "other_case": other,
                               "other_no": prev.invoice_no if prev else other})]
    return []


@check("advance_billing", STAGE, PATH, "Period has started")
def advance_billing(ctx: CheckContext):
    p = ctx.invoice.period_start
    ref = ctx.invoice.invoice_date or ctx.today
    if p and p > ref:
        return [ctx.warn("ADVANCE_BILLING", "Billed before the period started", data={"period": _period(p)})]
    return []


@check("contract_amount", STAGE, PATH, "Amount matches the contract")
def contract_amount(ctx: CheckContext):
    c = _contract(ctx)
    if not c:
        return [ctx.ok("Not checked: no contract")]
    found = ctx.invoice.taxable_total or sum((l.taxable for l in ctx.invoice.lines), Decimal("0"))
    tol = ctx.aop.tolerance.contract_amount_pct
    if abs(found - c.amount_per_period) > c.amount_per_period * tol / 100:
        return [ctx.fail("CONTRACT_AMOUNT_MISMATCH", "Amount differs from the contract", evidence=ctx.ev("taxable_total"),
                         data={"contract": c.contract_id, "expected": fmt_inr(c.amount_per_period), "found": fmt_inr(found)})]
    return []


@check("contract_balance", STAGE, PATH, "Within the contract PO balance")
def contract_balance(ctx: CheckContext):
    if ctx.po is None:
        return [ctx.ok("Not checked: contract has no PO")]
    return balance_findings(ctx, ctx.po)

"""Stage 4c: PO-less. No PO to match, so: is that allowed, which GL account, who approves."""
from __future__ import annotations

from decimal import Decimal

from ap_agent.checks.framework import CheckContext, check
from ap_agent.core.models import Outcome
from ap_agent.core.money import fmt_inr

STAGE = "match"
PATH = {"po_less"}
SAME_ITEM = 0.90
SERVICE_CATEGORIES = {"utilities", "telecom"}
ANOMALY_RATIO = Decimal("3")
HISTORY_N = 6


@check("open_po_exists", STAGE, PATH, "No open PO covers this invoice")
def open_po_exists(ctx: CheckContext):
    v = ctx.vendor
    if not v:
        return []
    for po in ctx.repo.open_pos(v.vendor_id):
        for line in ctx.invoice.lines:
            if any(ctx.ai.similarity(line.description, pl.description) >= SAME_ITEM for pl in po.lines):
                ctx.scratch["reroute"] = "standard_po"
                f = ctx.warn("PO_EXISTS_FOR_PO_LESS", f"Open {po.po_number} matches; checking against it",
                             data={"po": po.po_number})
                f.stop = True
                return [f]
    return []


@check("category_allowed", STAGE, PATH, "Category may be bought without a PO")
def category_allowed(ctx: CheckContext):
    v = ctx.vendor
    category = v.category if v else "unknown"
    if category not in ctx.aop.po_less_allowed_categories:
        return [ctx.fail("PO_REQUIRED_FOR_CATEGORY", f"A PO is required for {category}",
                         data={"vendor": v.name if v else ctx.invoice.supplier_name,
                               "category": category.replace("_", " ")})]
    return [ctx.ok(f"{category.capitalize()} may be bought without a PO")]


@check("service_account", STAGE, PATH, "Service account registered")
def service_account(ctx: CheckContext):
    v, no = ctx.vendor, ctx.invoice.consumer_no
    if not v or (v.category not in SERVICE_CATEGORIES and not no):
        return [ctx.ok("No service account involved")]
    if not ctx.repo.service_account(v.vendor_id, no):
        return [ctx.fail("UNKNOWN_SERVICE_ACCOUNT", "Service account not registered", evidence=ctx.ev("consumer_no"),
                         data={"consumer_no": no or "not printed", "vendor": v.name})]
    return [ctx.ok(f"Service account {no} registered")]


@check("gl_coding", STAGE, PATH, "GL account chosen")
def gl_coding(ctx: CheckContext):
    ranked = sorted(ctx.ai.gl_code(ctx.invoice, ctx.repo.gl_accounts()), key=lambda r: -r[2])[:3]
    options = [{"gl_code": g, "cost_centre": cc, "confidence": c, "why": w} for g, cc, c, w in ranked]
    accounts = {a.gl_code: a for a in ctx.repo.gl_accounts()}
    if not ranked or ranked[0][2] < ctx.aop.confidence.gl_coding_min:
        shown = ", ".join(f"{o['gl_code']} {accounts[o['gl_code']].name if o['gl_code'] in accounts else ''} "
                          f"({o['confidence']:.0%})" for o in options) or "none"
        return [ctx.fail("GL_CODING_UNCERTAIN", "GL account unclear", data={"options": options},
                         detail=f"I could not choose a GL account with enough confidence. Best suggestions: {shown}.")]
    best = options[0]
    acct = accounts.get(best["gl_code"])
    ctx.scratch["gl"] = best | {"name": acct.name if acct else "", "budget_owner": acct.budget_owner if acct else ""}
    return [ctx.ok(f"Coded to GL {best['gl_code']} {acct.name if acct else ''}",
                   f"{best['confidence']:.0%} sure: {best['why']}. Cost centre {best['cost_centre']}.",
                   data={"options": options, "gl_code": best["gl_code"]})]


@check("amount_anomaly", STAGE, PATH, "Amount in line with this vendor's history")
def amount_anomaly(ctx: CheckContext):
    v, amount = ctx.vendor, ctx.invoice.grand_total
    if not v or amount is None:
        return []
    past = [h.grand_total for h in ctx.history.cases_for_vendor(v.vendor_id, exclude_case=ctx.case_id)
            if h.outcome is Outcome.APPROVED and h.grand_total][-HISTORY_N:]
    if len(past) < 3:
        return [ctx.ok("Not enough history to compare")]
    avg = sum(past, Decimal("0")) / len(past)
    ratio = amount / avg
    if ratio > ANOMALY_RATIO:
        return [ctx.fail("AMOUNT_ANOMALY", "Much higher than usual", evidence=ctx.ev("grand_total"), data={
            "amount": fmt_inr(amount), "ratio": f"{ratio:.1f}", "average": fmt_inr(avg), "vendor": v.name})]
    return [ctx.ok("Amount in line with history", f"{fmt_inr(amount)} vs a recent average of {fmt_inr(avg)}")]


@check("po_less_limit", STAGE, PATH, "Within the PO-less approval limit")
def po_less_limit(ctx: CheckContext):
    amount, limit = ctx.invoice.grand_total, ctx.aop.authority.po_less_auto_limit_inr
    if amount is not None and amount > limit:
        return [ctx.fail("NEEDS_SIGNOFF", "Above the PO-less limit; budget owner signs off",
                         data={"amount": fmt_inr(amount), "limit": fmt_inr(limit)})]
    return []

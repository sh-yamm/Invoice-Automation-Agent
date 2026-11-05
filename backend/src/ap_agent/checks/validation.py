"""Stage 3: is this a valid GST tax invoice, and does the maths add up? (India rule pack)"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from ap_agent.checks.framework import CheckContext, check
from ap_agent.core.constants import BUYER_GSTIN, BUYER_STATE
from ap_agent.core.money import fmt_inr
from ap_agent.rules.india.gstin import gstin_state, is_valid_gstin
from ap_agent.rules.india.words import words_to_amount

STAGE = "validate"
LINE_TOLERANCE = Decimal("0.50")
TOTAL_TOLERANCE = Decimal("1.00")
STALE_DAYS = 365
_IRN = re.compile(r"^[0-9a-fA-F]{64}$")


def _tax(inv) -> Decimal:
    return sum((x for x in (inv.cgst, inv.sgst, inv.igst) if x is not None), Decimal("0"))


# The buyer check runs first: if the reader swapped the two GSTINs, fix that before anything else uses them.
@check("buyer_gstin", STAGE, {"all"}, "Billed to Zentra Retail's GSTIN")
def buyer_gstin(ctx: CheckContext):
    inv = ctx.invoice
    if inv.supplier_gstin == BUYER_GSTIN and inv.buyer_gstin and inv.buyer_gstin != BUYER_GSTIN:
        inv.supplier_gstin, inv.buyer_gstin = inv.buyer_gstin, inv.supplier_gstin
        ctx.vendor = ctx.repo.vendor_by_gstin(inv.supplier_gstin)
        return [ctx.warn("GSTIN_SWAPPED_FIXED", "Supplier and buyer GSTINs were swapped; fixed",
                         evidence=ctx.ev("buyer_gstin"))]
    if inv.buyer_gstin and inv.buyer_gstin != BUYER_GSTIN:
        return [ctx.fail("WRONG_BUYER_GSTIN", "Billed to a different company",
                         evidence=ctx.ev("buyer_gstin"), data={"found": inv.buyer_gstin, "expected": BUYER_GSTIN})]
    return []


@check("rule46_fields", STAGE, {"all"}, "All mandatory GST invoice fields present")
def rule46_fields(ctx: CheckContext):
    inv = ctx.invoice
    missing = [label for label, value in [
        ("invoice number", inv.invoice_no), ("invoice date", inv.invoice_date),
        ("supplier GSTIN", inv.supplier_gstin), ("buyer GSTIN", inv.buyer_gstin),
        ("taxable value", inv.taxable_total), ("tax amount", inv.cgst or inv.sgst or inv.igst),
        ("invoice total", inv.grand_total), ("line items", inv.lines),
    ] if not value]
    # HSN/SAC is not treated as a reject reason: small suppliers may omit it, and line matching
    # falls back to descriptions. (Ledger ruling, Task 7.)
    if missing:
        return [ctx.fail("MISSING_MANDATORY_FIELD", "Mandatory GST fields missing",
                         data={"fields": ", ".join(missing)})]
    return []


@check("supplier_gstin", STAGE, {"all"}, "Supplier GSTIN is valid")
def supplier_gstin(ctx: CheckContext):
    g = ctx.invoice.supplier_gstin
    if g and not is_valid_gstin(g):
        return [ctx.fail("INVALID_GSTIN", "Supplier GSTIN is not valid", evidence=ctx.ev("supplier_gstin"),
                         data={"gstin": g})]
    return []


@check("gstin_state", STAGE, {"all"}, "GSTIN state matches the vendor master")
def gstin_state_check(ctx: CheckContext):
    g, v = ctx.invoice.supplier_gstin, ctx.vendor
    if v and g and is_valid_gstin(g) and gstin_state(g) != v.state_code:
        return [ctx.fail("GSTIN_STATE_MISMATCH", "GSTIN state differs from the vendor's registered state",
                         evidence=ctx.ev("supplier_gstin"),
                         data={"gstin_state": gstin_state(g), "master_state": v.state_code})]
    return []


@check("gstin_active", STAGE, {"all"}, "Supplier GST registration is active")
def gstin_active(ctx: CheckContext):
    v = ctx.vendor
    if v and v.gst_status != "active":
        return [ctx.fail("GSTIN_INACTIVE", "Supplier GST registration is not active",
                         data={"gstin": v.gstin, "status": v.gst_status})]
    return []


@check("einvoice_irn", STAGE, {"all"}, "E-invoice IRN present where required")
def einvoice_irn(ctx: CheckContext):
    v, inv = ctx.vendor, ctx.invoice
    if not v or not v.einvoice_required:
        return [ctx.ok("E-invoice not required for this vendor")]
    if not inv.irn:
        return [ctx.fail("EINVOICE_IRN_MISSING", "No e-invoice IRN or QR code", evidence=ctx.ev("irn"),
                         data={"vendor": v.name, "tax": fmt_inr(_tax(inv))})]
    if not _IRN.match(inv.irn.strip()):
        return [ctx.fail("INVALID_IRN", "IRN is not in the valid format", evidence=ctx.ev("irn"),
                         data={"irn": inv.irn})]
    return []


@check("tax_type", STAGE, {"all"}, "Correct GST type for the supply")
def tax_type(ctx: CheckContext):
    inv = ctx.invoice
    if not inv.supplier_gstin or not is_valid_gstin(inv.supplier_gstin):
        return [ctx.ok("Tax type not checked (no valid supplier GSTIN)")]
    supply_state = inv.place_of_supply_state or BUYER_STATE
    intra = gstin_state(inv.supplier_gstin) == supply_state
    has_cs = bool(inv.cgst) or bool(inv.sgst)
    has_i = bool(inv.igst)
    if intra and (has_i or not has_cs):
        found = "IGST" if has_i else "no CGST/SGST"
        return [ctx.fail("WRONG_TAX_TYPE", "IGST charged on a supply within the state", evidence=ctx.ev("igst"),
                         data={"supply_kind": "within the state", "expected": "CGST + SGST", "found": found})]
    if not intra and (has_cs or not has_i):
        found = "CGST + SGST" if has_cs else "no IGST"
        return [ctx.fail("WRONG_TAX_TYPE", "CGST/SGST charged on an inter-state supply", evidence=ctx.ev("cgst"),
                         data={"supply_kind": "between states", "expected": "IGST", "found": found})]
    kind = "CGST + SGST (same state)" if intra else "IGST (inter-state)"
    return [ctx.ok(f"Correct tax type: {kind}")]


@check("arithmetic", STAGE, {"all"}, "Line amounts, tax and total add up")
def arithmetic(ctx: CheckContext):
    inv = ctx.invoice
    problems = []
    for i, l in enumerate(inv.lines, start=1):
        if abs(l.qty * l.rate - l.taxable) > LINE_TOLERANCE:
            problems.append(f"line {i}: {l.qty} × {fmt_inr(l.rate)} = {fmt_inr(l.qty * l.rate)}, "
                            f"but the line shows {fmt_inr(l.taxable)}")
    lines_sum = sum((l.taxable for l in inv.lines), Decimal("0"))
    if inv.taxable_total is not None and inv.lines and abs(lines_sum - inv.taxable_total) > TOTAL_TOLERANCE:
        problems.append(f"lines add up to {fmt_inr(lines_sum)}, but the taxable value is {fmt_inr(inv.taxable_total)}")
    if inv.lines and all(l.gst_rate is not None for l in inv.lines):
        expected_tax = sum((l.taxable * l.gst_rate / 100 for l in inv.lines), Decimal("0"))
        if abs(expected_tax - _tax(inv)) > TOTAL_TOLERANCE:
            problems.append(f"tax should be {fmt_inr(expected_tax)}, but the invoice shows {fmt_inr(_tax(inv))}")
    if inv.taxable_total is not None and inv.grand_total is not None:
        expected_total = inv.taxable_total + _tax(inv) + (inv.round_off or 0)
        if abs(expected_total - inv.grand_total) > TOTAL_TOLERANCE:
            problems.append(f"taxable value + tax = {fmt_inr(expected_total)}, but the total is {fmt_inr(inv.grand_total)}")
    if problems:
        return [ctx.fail("ARITHMETIC_MISMATCH", "Amounts don't add up", evidence=ctx.ev("grand_total"),
                         data={"detail": "; ".join(problems)})]
    return []


@check("amount_in_words", STAGE, {"all"}, "Amount in words matches the figures")
def amount_in_words(ctx: CheckContext):
    inv = ctx.invoice
    words = words_to_amount(inv.amount_in_words)
    if inv.amount_in_words is None or words is None or inv.grand_total is None:
        return [ctx.ok("Amount in words not printed or not readable; figures used")]
    if abs(words - inv.grand_total) > TOTAL_TOLERANCE:
        return [ctx.fail("AMOUNT_WORDS_MISMATCH", "Amount in words differs from the figures",
                         evidence=ctx.ev("amount_in_words"),
                         data={"words_amount": fmt_inr(words), "figures_amount": fmt_inr(inv.grand_total)})]
    return []


@check("date_sanity", STAGE, {"all"}, "Invoice date is plausible")
def date_sanity(ctx: CheckContext):
    d = ctx.invoice.invoice_date
    if d is None:
        return [ctx.ok("No invoice date to check")]
    if d > ctx.today:
        return [ctx.fail("FUTURE_DATED_INVOICE", "Invoice is dated in the future", evidence=ctx.ev("invoice_date"),
                         data={"date": d.strftime("%d %b %Y")})]
    if d < ctx.today - timedelta(days=STALE_DAYS):
        return [ctx.warn("STALE_INVOICE_DATE", "Invoice is more than a year old", evidence=ctx.ev("invoice_date"),
                         data={"date": d.strftime("%d %b %Y"), "days": STALE_DAYS})]
    return []

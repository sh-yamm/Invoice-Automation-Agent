"""Stage 5: controls on every path: vendor, bank details, duplicates, split-to-avoid-limit, authority."""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from rapidfuzz.distance import Levenshtein

from ap_agent.checks.framework import CheckContext, check
from ap_agent.core.constants import OUTCOME_LABELS
from ap_agent.core.models import Outcome
from ap_agent.core.money import fmt_inr
from ap_agent.rules.normalise import normal_invoice_no

STAGE = "controls"
ALL = {"all"}
LOOKALIKE_MIN = 0.85
IDENTITY_MIN = 0.60
AMOUNT_TOL = Decimal("0.005")   # 0.5%
NUMBER_EDITS = 2
OPEN_STATUSES = {"running", "waiting", "waiting_vendor"}


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _masked(account: str, last: int = 4) -> str:
    d = _digits(account)
    return f"****{d[-last:]}" if d else "not printed"


def _same_amount(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and b != 0 and abs(a - b) <= abs(b) * AMOUNT_TOL


def _is_open(h) -> bool:
    return h.outcome is not Outcome.REJECTED and (h.outcome is Outcome.APPROVED or h.status in OPEN_STATUSES
                                                  or h.outcome in (Outcome.ON_HOLD, Outcome.NEEDS_SIGNOFF))


def _label(h) -> str:
    return OUTCOME_LABELS[int(h.outcome)].lower() if h.outcome is not None else "still in progress"


def _history(ctx):
    v = ctx.vendor
    return ctx.history.cases_for_vendor(v.vendor_id, exclude_case=ctx.case_id) if v else []


@check("vendor_approved", STAGE, ALL, "Vendor is approved in the vendor master")
def vendor_approved(ctx: CheckContext):
    v, inv = ctx.vendor, ctx.invoice
    if v is None or v.status != "active":
        return [ctx.fail("VENDOR_NOT_APPROVED", "Vendor not in the vendor master", evidence=ctx.ev("supplier_gstin"),
                         data={"vendor": inv.supplier_name or "Unknown supplier", "gstin": inv.supplier_gstin or "—"})]
    return [ctx.ok(f"{v.name} is an approved vendor")]


@check("lookalike_vendor", STAGE, ALL, "Not imitating a known vendor")
def lookalike_vendor(ctx: CheckContext):
    if ctx.vendor is not None or not ctx.invoice.supplier_name:
        return []
    name = ctx.invoice.supplier_name
    best = max(((ctx.ai.similarity(name, v.name), v) for v in ctx.repo.vendors()), key=lambda s: s[0], default=None)
    if best and best[0] >= LOOKALIKE_MIN:
        return [ctx.fail("LOOKALIKE_VENDOR", f"Name resembles approved vendor {best[1].name}",
                         evidence=ctx.ev("supplier_name"),
                         data={"vendor": name, "similar": best[1].name, "similarity": round(best[0], 2)})]
    return []


@check("vendor_identity", STAGE, ALL, "Vendor name and contact details match the master")
def vendor_identity(ctx: CheckContext):
    v, inv = ctx.vendor, ctx.invoice
    if v is None:
        return []
    out = []
    if inv.supplier_name and ctx.ai.similarity(inv.supplier_name, v.name) < IDENTITY_MIN:
        out.append(ctx.warn("VENDOR_IDENTITY_MISMATCH", "Name differs from the vendor master",
                            data={"found": inv.supplier_name, "expected": v.name}))
    changed = []
    if inv.supplier_phone and _digits(inv.supplier_phone)[-10:] != _digits(v.phone)[-10:]:
        changed.append(("phone", inv.supplier_phone, v.phone))
    if inv.supplier_email and inv.supplier_email.strip().lower() != v.email.lower():
        changed.append(("email", inv.supplier_email, v.email))
    if changed:
        out.append(ctx.warn("CONTACT_DETAILS_CHANGED", "Contact details differ from the vendor master", data={
            "found": ", ".join(f"{k} {a}" for k, a, _ in changed),
            "expected": ", ".join(f"{k} {b}" for k, _, b in changed)}))
    return out


@check("bank_details", STAGE, ALL, "Bank details match the vendor master")
def bank_details(ctx: CheckContext):
    v, inv = ctx.vendor, ctx.invoice
    if v is None:
        return [ctx.ok("Bank details not compared (vendor not in master)")]
    if not inv.bank_account and not inv.ifsc:
        return [ctx.ok("Bank details not printed; the master account will be used")]
    mismatch = False
    if inv.bank_account:
        printed = _digits(inv.bank_account)
        masked = bool(re.search(r"[*xX]", inv.bank_account))
        master = _digits(v.bank_account)
        mismatch = not master.endswith(printed) if masked else printed != master
    if inv.ifsc and inv.ifsc.strip().upper() != v.ifsc.upper():
        mismatch = True
    if mismatch:
        return [ctx.fail("BANK_DETAILS_MISMATCH", "Bank account differs from the vendor master",
                         evidence=ctx.ev("bank_account"), data={
                             "vendor": v.name,
                             "invoice_bank": f"{inv.bank_name or 'a bank'} A/c {_masked(inv.bank_account)}",
                             "master_bank": f"{v.bank_name} A/c {_masked(v.bank_account)}"})]
    return [ctx.ok(f"Bank details match ({v.bank_name} A/c {_masked(v.bank_account)})")]


@check("duplicate_exact", STAGE, ALL, "Not a duplicate invoice number")
def duplicate_exact(ctx: CheckContext):
    inv = ctx.invoice
    norm = normal_invoice_no(inv.invoice_no)
    if not norm:
        return []
    for h in _history(ctx):
        if h.invoice_no_norm != norm or h.outcome is Outcome.REJECTED:
            continue
        data = {"other_case": h.case_id, "other_no": h.invoice_no, "other_outcome": _label(h),
                "invoice_no": inv.invoice_no, "amount": fmt_inr(inv.grand_total or 0),
                "other_amount": fmt_inr(h.grand_total or 0)}
        if not _same_amount(inv.grand_total, h.grand_total):
            return [ctx.fail("DUPLICATE_NUMBER_DIFFERENT_AMOUNT", "Invoice number already used, different amount",
                             evidence=ctx.ev("invoice_no"), data=data)]
        f = ctx.fail("DUPLICATE_EXACT", f"Same invoice as {h.invoice_no}", evidence=ctx.ev("invoice_no"), data=data)
        if h.outcome is not Outcome.APPROVED:
            f.outcome = Outcome.ON_HOLD  # the original is still being processed; hold rather than reject
        return [f]
    return []


def _line_similarity(ctx, texts: list[str]) -> float:
    lines = [l.description for l in ctx.invoice.lines]
    if not lines or not texts:
        return 0.0
    return sum(max(ctx.ai.similarity(a, b) for b in texts) for a in lines) / len(lines)


@check("duplicate_fuzzy", STAGE, ALL, "Not a resend of an earlier invoice")
def duplicate_fuzzy(ctx: CheckContext):
    inv = ctx.invoice
    norm = normal_invoice_no(inv.invoice_no)
    window = ctx.aop.duplicates.window_days
    min_sim = ctx.aop.duplicates.min_similarity_pct / 100
    mine = {(ctx.po.po_number, p.po_line_no) for p in ctx.pairs if p.po_line_no} if ctx.po else set()
    best = None
    for h in _history(ctx):
        theirs = ctx.ledger.lines_for_case(h.case_id)
        if mine and theirs and mine.isdisjoint(theirs):
            continue  # bills different PO lines: a separate delivery, not a resend (ledger ruling, Task 13)
        if norm and h.invoice_no_norm == norm and h.outcome is not Outcome.REJECTED:
            continue  # handled by duplicate_exact
        if not _same_amount(inv.grand_total, h.grand_total):
            continue  # a real resend bills the same amount (ledger ruling, Task 11)
        if ctx.txn_type == "recurring" and inv.period_start and h.period_start and h.period_start != inv.period_start:
            continue  # next month's retainer is not a duplicate
        reasons = ["same amount"]
        if norm and h.invoice_no_norm and Levenshtein.distance(norm, h.invoice_no_norm) <= NUMBER_EDITS:
            reasons.append(f"invoice number {h.invoice_no} is almost the same")
        if inv.invoice_date and h.invoice_date and abs((inv.invoice_date - h.invoice_date).days) <= window:
            reasons.append(f"dated {abs((inv.invoice_date - h.invoice_date).days)} days apart")
        if _line_similarity(ctx, h.line_texts) >= min_sim:
            reasons.append("same line items")
        if len(reasons) >= 2 and (best is None or len(reasons) > len(best[1])):
            best = (h, reasons)
    if not best:
        return []
    h, reasons = best
    data = {"other_case": h.case_id, "other_no": h.invoice_no, "other_outcome": _label(h), "reasons": ", ".join(reasons)}
    if h.outcome is Outcome.REJECTED:
        return [ctx.warn("RESUBMISSION_OF_REJECTED", f"Resembles rejected invoice {h.invoice_no}",
                         data=data | {"reason": "rejected earlier"})]
    return [ctx.fail("DUPLICATE_PROBABLE", f"Looks like a resend of {h.invoice_no}", evidence=ctx.ev("invoice_no"),
                     data=data)]


@check("split_below_limit", STAGE, ALL, "Not split to stay under the approval limit")
def split_below_limit(ctx: CheckContext):
    inv, limit = ctx.invoice, ctx.aop.authority.auto_approve_limit_inr
    days = ctx.aop.authority.split_window_days
    if inv.grand_total is None or inv.grand_total > limit or not inv.invoice_date:
        return []
    others = [h for h in _history(ctx) if _is_open(h) and h.grand_total is not None and h.grand_total <= limit
              and h.invoice_date and abs((inv.invoice_date - h.invoice_date).days) <= days]
    total = inv.grand_total + sum((h.grand_total for h in others), Decimal("0"))
    if others and total > limit:
        return [ctx.fail("SPLIT_BELOW_LIMIT", f"{len(others) + 1} invoices in {days} days add up to {fmt_inr(total)}",
                         data={"vendor": ctx.vendor.name, "count": len(others) + 1, "days": days,
                               "limit": fmt_inr(limit), "total": fmt_inr(total),
                               "cases": [h.case_id for h in others]})]
    return []


@check("authority", STAGE, ALL, "Within the agent's approval limit")
def authority(ctx: CheckContext):
    amount, limit = ctx.invoice.grand_total, ctx.aop.authority.auto_approve_limit_inr
    if amount is not None and amount > limit:
        return [ctx.fail("NEEDS_SIGNOFF", "Above my approval limit; finance controller signs off",
                         data={"amount": fmt_inr(amount), "limit": fmt_inr(limit)})]
    return [ctx.ok(f"Within my {fmt_inr(limit)} approval limit")]

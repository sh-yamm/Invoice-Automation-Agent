"""Stage 4a: Standard PO. Match the invoice to its PO line by line; goods also against the receipt (3-way)."""
from __future__ import annotations

from decimal import Decimal

from ap_agent.checks.framework import CheckContext, LinePair, check
from ap_agent.core.money import fmt_inr, to_money
from ap_agent.rules.normalise import convert_qty

STAGE = "match"
PATH = {"standard_po"}
PAIR_MIN = 0.80
LEAD_MIN = 0.10


def _no_po(ctx):
    return [ctx.ok("Not checked: no PO matched")] if ctx.po is None else None


def _paired(ctx):
    """(invoice line, PO line, qty in PO units, rate per PO unit) for every line-level pair."""
    conv = ctx.scratch.get("conv", {})
    for p in ctx.pairs:
        if p.po_line_no is None or p.method == "header":
            continue
        line = ctx.invoice.lines[p.inv_index]
        po_line = ctx.po.line(p.po_line_no)
        qty, rate = conv.get(p.inv_index, (line.qty, line.rate))
        yield p.inv_index, line, po_line, qty, rate


def _billed_before(ctx, line_no):
    return ctx.ledger.invoiced(ctx.po.po_number, line_no)[0]


def _pct(a: Decimal, b: Decimal) -> float:
    return float(round((a - b) / b * 100, 2)) if b else 0.0


@check("po_resolve", STAGE, PATH, "Purchase order found")
def po_resolve(ctx: CheckContext):
    inv, v = ctx.invoice, ctx.vendor
    printed = ctx.repo.po(inv.po_ref) if inv.po_ref else None
    if printed:
        ctx.po = printed
        return [ctx.ok(f"{printed.po_number} found", "Quoted on the invoice", ctx.ev("po_ref"),
                       {"po": printed.po_number})]
    reason = f"{inv.po_ref} is not in the PO system" if inv.po_ref else "no PO number is printed"
    candidates = ctx.repo.open_pos(v.vendor_id) if v else []
    if not candidates:
        return [ctx.fail("PO_NOT_FOUND", "No purchase order matched", stop=True,
                         data={"reason": reason + " and the vendor has no open POs"})]
    ranking = sorted(ctx.ai.rank_po_candidates(inv, candidates), key=lambda r: -r[1])
    best = ranking[0] if ranking else None
    runner = ranking[1][1] if len(ranking) > 1 else 0.0
    if best and best[1] >= ctx.aop.confidence.po_inference_min and best[1] - runner >= LEAD_MIN:
        ctx.po = ctx.repo.po(best[0])
        return [ctx.warn("PO_INFERRED", f"PO not printed; matched to {best[0]}", evidence=ctx.ev("po_ref"),
                         data={"po": best[0], "confidence": f"{best[1]:.0%}", "why": best[2]})]
    listed = ", ".join(f"{p} ({s:.0%})" for p, s, _ in ranking[:3]) or "none"
    return [ctx.fail("PO_NOT_FOUND", "No purchase order matched", stop=True,
                     data={"reason": f"{reason}; candidates: {listed}", "candidates": ranking[:3]})]


@check("po_vendor", STAGE, PATH, "PO was issued to this vendor")
def po_vendor(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    v = ctx.vendor
    if v and ctx.po.vendor_id != v.vendor_id:
        other = ctx.repo.vendor(ctx.po.vendor_id)
        return [ctx.fail("PO_VENDOR_MISMATCH", "PO belongs to a different vendor", evidence=ctx.ev("po_ref"),
                         stop=True, data={"po": ctx.po.po_number, "po_vendor": other.name if other else ctx.po.vendor_id,
                                          "vendor": v.name})]
    return []


@check("po_open", STAGE, PATH, "PO is open")
def po_open(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    if ctx.po.status != "open":
        return [ctx.fail("PO_CLOSED", "PO is not open", data={"po": ctx.po.po_number, "status": ctx.po.status})]
    return []


@check("line_pairing", STAGE, PATH, "Every invoice line matches a PO line")
def line_pairing(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    inv, po = ctx.invoice, ctx.po
    if len(inv.lines) == 1 and len(po.lines) >= 2:
        ctx.pairs = [LinePair(0, None, "header", 1.0)]
        return [ctx.warn("HEADER_LEVEL_MATCH_ONLY", "One combined line; checked against the PO total")]
    out, taken, unpaired = [], set(), []
    for i, line in enumerate(inv.lines):
        free = [pl for pl in po.lines if pl.line_no not in taken]
        scored = sorted(((ctx.ai.similarity(line.description, pl.description), pl) for pl in free),
                        key=lambda s: -s[0])
        same_hsn = [(s, pl) for s, pl in scored if line.hsn_sac and pl.hsn_sac == line.hsn_sac and s >= PAIR_MIN]
        if same_hsn:
            pair = LinePair(i, same_hsn[0][1].line_no, "hsn", same_hsn[0][0])
        elif scored and scored[0][0] >= PAIR_MIN:
            pair = LinePair(i, scored[0][1].line_no, "similarity", scored[0][0])
        else:
            line_no, conf, why = ctx.ai.pair_tiebreak(line, free) if free else (None, 0.0, "")
            if line_no is not None and conf >= PAIR_MIN and line_no not in taken:
                pair = LinePair(i, line_no, "agent", conf)
                out.append(ctx.warn("LLM_LINE_PAIRING", "Line matched by the agent", data={
                    "item": line.description, "po_line": line_no, "confidence": f"{conf:.0%}", "why": why}))
            else:
                pair = LinePair(i, None, "none", 0.0)
                unpaired.append(line)
        if pair.po_line_no is not None:
            taken.add(pair.po_line_no)
        ctx.pairs.append(pair)
    if unpaired:
        out.append(ctx.fail("UNEXPECTED_CHARGES", "Invoice lines not on the PO", data={
            "po": po.po_number, "lines": ", ".join(f"{l.description} ({fmt_inr(l.taxable)})" for l in unpaired)}))
    return out


@check("gst_rate", STAGE, PATH, "GST rates match the PO")
def gst_rate(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    out = []
    for _, line, pl, _, _ in _paired(ctx):
        if line.gst_rate is not None and line.gst_rate != pl.gst_rate:
            out.append(ctx.fail("GST_RATE_MISMATCH", f"GST rate differs on {line.description}", data={
                "item": line.description, "billed": f"{line.gst_rate:g}", "po_rate": f"{pl.gst_rate:g}"}))
    return out


@check("units", STAGE, PATH, "Units match or convert")
def units(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    out, conv = [], ctx.scratch.setdefault("conv", {})
    for p in ctx.pairs:
        if p.po_line_no is None or p.method == "header":
            continue
        line, pl = ctx.invoice.lines[p.inv_index], ctx.po.line(p.po_line_no)
        qty = convert_qty(line.qty, line.unit, pl.unit)
        if qty is None:
            out.append(ctx.fail("UNIT_MISMATCH", f"Units can't be converted for {line.description}", data={
                "item": line.description, "inv_unit": line.unit, "po_unit": pl.unit}))
            conv[p.inv_index] = (line.qty, line.rate)
        elif qty:
            conv[p.inv_index] = (qty, line.taxable / qty)
    return out


@check("price", STAGE, PATH, "Prices within tolerance of the PO")
def price(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    tol = ctx.aop.tolerance.price
    out, variances = [], []
    for _, line, pl, qty, rate in _paired(ctx):
        pct = _pct(rate, pl.rate)
        excess = (rate - pl.rate) * qty
        variances.append({"item": line.description, "variance_pct": pct, "excess": str(to_money(excess))})
        data = {"vendor": ctx.vendor.name if ctx.vendor else ctx.invoice.supplier_name, "item": line.description,
                "billed_rate": fmt_inr(rate), "po_rate": fmt_inr(pl.rate), "pct": f"{pct:.1f}",
                "abs": fmt_inr(excess), "tol": f"{tol.over_pct}", "variance_pct": pct}
        if rate > pl.rate * (1 + tol.over_pct / 100) or excess > tol.over_abs_inr:
            out.append(ctx.fail("PRICE_VARIANCE", f"{line.description}: rate {pct:.1f}% above the PO",
                                evidence=ctx.ev("lines"), data=data))
        elif rate < pl.rate:
            out.append(ctx.warn("UNDER_BILLED", f"{line.description}: billed below the PO rate", data=data))
    if not out:
        worst = max((v["variance_pct"] for v in variances), default=0.0)
        out.append(ctx.ok("Prices within tolerance of the PO", f"Largest variance {worst:.1f}%",
                          data={"variances": variances}))
    else:
        out[0].data["variances"] = variances
    return out


@check("qty_ordered", STAGE, PATH, "Quantities within what was ordered")
def qty_ordered(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    tol = ctx.aop.tolerance.qty_over_ordered_pct
    out = []
    for _, line, pl, qty, _ in _paired(ctx):
        total = _billed_before(ctx, pl.line_no) + qty
        if total > pl.qty * (1 + tol / 100):
            out.append(ctx.fail("QTY_EXCEEDS_ORDERED", f"{line.description}: more than ordered", data={
                "item": line.description, "billed": f"{total:g} {pl.unit}", "ordered": f"{pl.qty:g} {pl.unit}",
                "po": ctx.po.po_number}))
    return out


@check("grn_exists", STAGE, PATH, "Goods receipt recorded")
def grn_exists(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    if ctx.po.po_type != "goods":
        return [ctx.ok("Goods receipt not required (2-way match for services)")]
    out = []
    for _, line, pl, _, _ in _paired(ctx):
        if not ctx.repo.grns(ctx.po.po_number, pl.line_no):
            out.append(ctx.fail("RECEIPT_MISSING", f"No goods receipt for {line.description}",
                                data={"item": line.description, "po": ctx.po.po_number}))
    return out


@check("qty_received", STAGE, PATH, "Quantities within what was received")
def qty_received(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    if ctx.po.po_type != "goods":
        return [ctx.ok("Receipt quantities not required (2-way match for services)")]
    tol = ctx.aop.tolerance.qty_over_received_pct
    out = []
    for _, line, pl, qty, _ in _paired(ctx):
        grns = ctx.repo.grns(ctx.po.po_number, pl.line_no)
        if not grns:
            continue  # reported by grn_exists
        accepted = sum((g.accepted_qty for g in grns), Decimal("0"))
        total = _billed_before(ctx, pl.line_no) + qty
        if total > accepted * (1 + tol / 100):
            out.append(ctx.fail("QTY_EXCEEDS_RECEIVED", f"{line.description}: more than received", data={
                "item": line.description, "billed": f"{total:g} {pl.unit}", "received": f"{accepted:g} {pl.unit}",
                "grn": ", ".join(sorted({g.grn_number for g in grns}))}))
    return out


@check("po_balance", STAGE, PATH, "Within the PO's remaining balance")
def po_balance(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    value = ctx.po.value
    invoiced = ctx.ledger.invoiced(ctx.po.po_number)[1]
    this = ctx.invoice.taxable_total or sum((l.taxable for l in ctx.invoice.lines), Decimal("0"))
    data = {"po": ctx.po.po_number, "po_value": fmt_inr(value), "invoiced": fmt_inr(invoiced),
            "remaining": fmt_inr(max(value - invoiced, Decimal("0"))), "this_amount": fmt_inr(this),
            "over": fmt_inr(invoiced + this - value)}
    if invoiced >= value:
        return [ctx.fail("PO_FULLY_INVOICED", "PO already fully invoiced", data=data)]
    if invoiced + this > value * (1 + ctx.aop.tolerance.po_balance_over_pct / 100):
        return [ctx.fail("AMOUNT_EXCEEDS_PO_BALANCE", "Invoice exceeds the PO balance", evidence=ctx.ev("taxable_total"),
                         data=data)]
    return [ctx.ok("Within the PO's remaining balance", f"{data['remaining']} remaining before this invoice",
                   data=data)]


@check("invoice_before_po", STAGE, PATH, "Invoice dated after the PO")
def invoice_before_po(ctx: CheckContext):
    if (skip := _no_po(ctx)):
        return skip
    d = ctx.invoice.invoice_date
    if d and d < ctx.po.po_date:
        return [ctx.fail("INVOICE_BEFORE_PO", "Invoice dated before the PO was raised", evidence=ctx.ev("invoice_date"),
                         data={"inv_date": d.strftime("%d %b %Y"), "po": ctx.po.po_number,
                               "po_date": ctx.po.po_date.strftime("%d %b %Y")})]
    return []

"""Rates printed with GST already included.

Some vendors print each line's rate and amount with GST included, and show the taxable value and the GST only in
the summary. Read as printed, every rate looks about 18% above the PO's (which is before GST) and the lines don't
add up to the taxable value. The rates are converted only when the invoice's own numbers prove they include GST:

- the lines add up to the invoice total *with* GST, and GST is shown separately;
- converting each line at its own GST rate gives lines that add up to the taxable value (when it is printed), and
  that plus the GST shown is the invoice total.

If GST isn't shown at all, nothing is converted: such a document isn't a valid tax invoice, and the mandatory-field
check must still see that. Nothing is guessed: a line without a GST rate stops the conversion.
"""
from __future__ import annotations

from decimal import Decimal

from ap_agent.core.models import Invoice
from ap_agent.rules.normalise import to_exclusive

TOLERANCE = Decimal("1.00")
_CENT = Decimal("0.01")


LINE_TOLERANCE = Decimal("0.50")


def normalise_inclusive(inv: Invoice) -> tuple[Invoice, dict | None]:
    """The invoice with before-GST rates, and what was converted; or the invoice unchanged and None.

    Each line is read in one of three ways, and anything else stops the conversion:
    - rate and amount on the same basis (qty × rate = amount): both with GST if the lines add up to the total with
      GST, otherwise both already before GST;
    - rate with GST but amount before GST (qty × rate = amount plus GST): only the rate is converted.
    """
    if not inv.lines or inv.grand_total is None:
        return inv, None
    if any(l.gst_rate is None or l.rate is None or l.taxable is None or l.qty is None for l in inv.lines):
        return inv, None
    tax = sum((x for x in (inv.cgst, inv.sgst, inv.igst) if x is not None), Decimal("0"))
    if tax <= 0:
        return inv, None
    round_off = inv.round_off or Decimal("0")
    printed = sum((l.taxable for l in inv.lines), Decimal("0"))
    lines_with_gst = abs(printed - (inv.grand_total - round_off)) <= TOLERANCE
    converted = []  # (rate, amount) before GST, per line
    for l in inv.lines:
        if abs(l.qty * l.rate - l.taxable) <= LINE_TOLERANCE:
            converted.append((to_exclusive(l.rate, l.gst_rate), to_exclusive(l.taxable, l.gst_rate))
                             if lines_with_gst else (l.rate, l.taxable))
        elif abs(l.qty * l.rate - l.taxable * (1 + l.gst_rate / 100)) <= LINE_TOLERANCE:
            converted.append((to_exclusive(l.rate, l.gst_rate), l.taxable))
        else:
            return inv, None
    if all(r == l.rate and a == l.taxable for (r, a), l in zip(converted, inv.lines)):
        return inv, None  # nothing included GST
    before_gst = sum((a for _, a in converted), Decimal("0"))
    if abs(before_gst + tax + round_off - inv.grand_total) > TOLERANCE:
        return inv, None
    if inv.taxable_total is not None and abs(before_gst - inv.taxable_total) > TOLERANCE:
        return inv, None
    with_gst = before_gst + tax
    out = inv.model_copy(deep=True)
    for line, (rate, amount) in zip(out.lines, converted):
        line.rate, line.taxable = rate, amount
    if out.taxable_total is None:
        out.taxable_total = before_gst
    return out, {"lines": len(out.lines), "before_gst": str(before_gst.quantize(_CENT)),
                 "with_gst": str(with_gst.quantize(_CENT))}

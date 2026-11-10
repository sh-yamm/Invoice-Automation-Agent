"""Recover a total or tax amount the page reader missed, from the PDF's own embedded text.

The page parser sometimes drops the last rows of a dense totals table (most often "Invoice Total" when the
amount in words sits beside it). A digital PDF still carries those figures in its text layer. A figure is taken
from there only when it is exactly what the invoice's own numbers require:

  * tax: taxable value x the GST rate on the lines (CGST and SGST as two halves within the state, IGST across);
  * total: taxable value + tax + round-off, and the same amount as the amount in words, when that is printed.

So a figure planted in hidden text (demo S13's "Invoice total 29,169.60") can never fill a gap: it does not add
up. Scanned copies have no text layer, so nothing is recovered for them.
"""
from __future__ import annotations

import re
from decimal import Decimal

from ap_agent.core.models import Evidence, Invoice, ParseBlock
from ap_agent.rules.india.words import words_to_amount
from ap_agent.rules.normalise import parse_inr

_NUM = re.compile(r"\d[\d,]*\.\d{2}\b|\d{1,3}(?:,\d{2,3})+\b")
CENT = Decimal("0.01")


def _amounts(blocks: list[ParseBlock]) -> list[tuple[Decimal, ParseBlock]]:
    out = []
    for b in blocks:
        for m in _NUM.findall(b.text):
            v = parse_inr(m)
            if v is not None:
                out.append((Decimal(v).quantize(CENT), b))
    return out


def _find(amounts, value: Decimal) -> ParseBlock | None:
    v = value.quantize(CENT)
    return next((b for a, b in amounts if a == v), None)


def _intra_state(inv: Invoice) -> bool:
    supplier = (inv.supplier_gstin or "")[:2]
    place = inv.place_of_supply_state or (inv.buyer_gstin or "")[:2]
    return bool(supplier) and supplier == place


def _taxable(inv: Invoice) -> Decimal | None:
    if inv.taxable_total:
        return inv.taxable_total
    return sum((l.taxable for l in inv.lines), Decimal("0")) or None


def _expected_tax(inv: Invoice) -> Decimal | None:
    if not inv.lines or any(l.gst_rate is None for l in inv.lines):
        return None
    return sum((l.taxable * l.gst_rate / 100 for l in inv.lines), Decimal("0")).quantize(CENT)


def _keep(inv: Invoice, field: str, value: Decimal, block: ParseBlock) -> None:
    setattr(inv, field, value)
    inv.confidence[field] = 0.9
    inv.sources[field] = Evidence(field=field, page=block.page, box=block.box, text=block.text[:120])


def recover_totals(invoice: Invoice, text_blocks: list[ParseBlock]) -> tuple[Invoice, list[str]]:
    """Fill a missing tax amount or invoice total from the PDF's text layer, when the figure adds up.
    Returns the invoice (a copy) and the fields recovered, in the order they were filled."""
    inv = invoice.model_copy(deep=True)
    if not text_blocks:
        return inv, []
    amounts = _amounts(text_blocks)
    got: list[str] = []
    taxable = _taxable(inv)

    if taxable and not any((inv.cgst, inv.sgst, inv.igst)):
        tax = _expected_tax(inv)
        if tax:
            if _intra_state(inv):
                half = (tax / 2).quantize(CENT)
                b = _find(amounts, half)
                if b:
                    _keep(inv, "cgst", half, b)
                    _keep(inv, "sgst", half, b)
                    got += ["cgst", "sgst"]
            else:
                b = _find(amounts, tax)
                if b:
                    _keep(inv, "igst", tax, b)
                    got.append("igst")

    if inv.grand_total is None and taxable and any((inv.cgst, inv.sgst, inv.igst)):
        total = (taxable + (inv.cgst or 0) + (inv.sgst or 0) + (inv.igst or 0) + (inv.round_off or 0)).quantize(CENT)
        words = words_to_amount(inv.amount_in_words) if inv.amount_in_words else None
        b = _find(amounts, total)
        if b and (words is None or Decimal(words).quantize(CENT) == total):
            _keep(inv, "grand_total", total, b)
            got.append("grand_total")
    return inv, got

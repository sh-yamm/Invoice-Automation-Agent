"""Grounding: every value the reader returned must actually appear on the page.

This is the main defence against a model inventing a PO number or an amount. A value that cannot be
found in any parsed block is removed (set to None, confidence 0) and reported. Found values get a
source location, which the UI uses to highlight evidence on the page.
"""
from __future__ import annotations

import re
from decimal import Decimal

from ap_agent.core.models import Evidence, Finding, Invoice, ParseBlock, Status
from ap_agent.rules.normalise import parse_date_in, parse_inr

STRING_FIELDS = {"invoice_no": "invoice number", "po_ref": "PO number", "supplier_gstin": "supplier GSTIN",
                 "buyer_gstin": "buyer GSTIN", "irn": "IRN", "bank_account": "bank account", "ifsc": "IFSC",
                 "consumer_no": "account number"}
AMOUNT_FIELDS = {"taxable_total": "taxable value", "cgst": "CGST", "sgst": "SGST", "igst": "IGST",
                 "grand_total": "invoice total"}
DATE_FIELDS = {"invoice_date": "invoice date"}

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DATE = re.compile(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}")


def _alnum(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _snippet(b: ParseBlock) -> str:
    return b.text if len(b.text) <= 120 else b.text[:117] + "…"


def _find(blocks: list[ParseBlock], match) -> ParseBlock | None:
    return next((b for b in blocks if match(b)), None)


def ground(invoice: Invoice, blocks: list[ParseBlock]) -> tuple[Invoice, list[Finding]]:
    inv = invoice.model_copy(deep=True)
    amounts = {id(b): {parse_inr(n) for n in _NUM.findall(b.text)} for b in blocks}
    dates = {id(b): {parse_date_in(d) for d in _DATE.findall(b.text)} for b in blocks}
    alnum = {id(b): _alnum(b.text) for b in blocks}
    missing: list[str] = []

    def keep(field, block):
        inv.sources[field] = Evidence(field=field, page=block.page, box=block.box, text=_snippet(block))

    def drop(field, label, value):
        setattr(inv, field, None)
        inv.confidence[field] = 0.0
        missing.append(f"{label} {value}")

    for field, label in STRING_FIELDS.items():
        v = getattr(inv, field)
        if not v:
            continue
        target = _alnum(v)
        b = _find(blocks, lambda b: target and target in alnum[id(b)])
        keep(field, b) if b else drop(field, label, v)
    for field, label in AMOUNT_FIELDS.items():
        v = getattr(inv, field)
        if v is None or v == 0:
            continue
        b = _find(blocks, lambda b: any(a is not None and a == Decimal(v) for a in amounts[id(b)]))
        keep(field, b) if b else drop(field, label, v)
    for field, label in DATE_FIELDS.items():
        v = getattr(inv, field)
        if v is None:
            continue
        b = _find(blocks, lambda b: v in dates[id(b)])
        keep(field, b) if b else drop(field, label, v.strftime("%d/%m/%Y"))
    table = _find(blocks, lambda b: b.cls == "Table" and any(l.description[:12].lower() in b.text.lower()
                                                               for l in inv.lines))
    if table:
        keep("lines", table)

    if missing:
        fields = ", ".join(missing)
        return inv, [Finding(check="grounding", stage="read", status=Status.WARN, code="UNGROUNDED_VALUE",
                             title="Values not found on the page were removed",
                             detail=f"I removed {fields} because I could not find them on the page.",
                             data={"fields": fields})]
    return inv, [Finding(check="grounding", stage="read", status=Status.PASS,
                         title="Every value was found on the page")]

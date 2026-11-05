"""Domain models shared by every part of the pipeline."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class Outcome(IntEnum):
    """Case outcome, ordered by severity: a higher value always wins."""

    APPROVED = 0
    NEEDS_SIGNOFF = 1
    ON_HOLD = 2
    REJECTED = 3


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Evidence(BaseModel):
    field: str
    page: int | None = None
    box: tuple[float, float, float, float] | None = None
    text: str | None = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    check: str
    stage: str
    status: Status
    code: str | None = None
    outcome: Outcome | None = None
    title: str
    detail: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    stop: bool = False


class Line(BaseModel):
    description: str
    hsn_sac: str | None = None
    qty: Decimal
    unit: str | None = None
    rate: Decimal
    taxable: Decimal
    gst_rate: Decimal | None = None


class Invoice(BaseModel):
    """An invoice as read from the document, after normalisation."""

    doc_title: str | None = None
    supplier_name: str | None = None
    supplier_gstin: str | None = None
    supplier_phone: str | None = None
    supplier_email: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    po_ref: str | None = None
    place_of_supply_state: str | None = None
    irn: str | None = None
    has_qr: bool = False
    bank_name: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None
    lines: list[Line] = Field(default_factory=list)
    taxable_total: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    round_off: Decimal | None = None
    grand_total: Decimal | None = None
    amount_in_words: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    consumer_no: str | None = None
    confidence: dict[str, float] = Field(default_factory=dict)
    sources: dict[str, Evidence] = Field(default_factory=dict)


class ParseBlock(BaseModel):
    """One text block from the page parser, with a box normalised to 0–1."""

    page: int
    text: str
    box: tuple[float, float, float, float]
    cls: str = "Text"

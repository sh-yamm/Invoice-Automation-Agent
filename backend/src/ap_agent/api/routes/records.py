"""People's changes to the company records: approved vendors and purchase orders (see erp/records.py)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ap_agent.api.common import J, ctx_of
from ap_agent.erp import records

router = APIRouter(prefix="/api")


class Who(BaseModel):
    actor: str = "AP lead"
    why: str = ""


class NewVendor(Who):
    name: str
    gstin: str
    address: str = ""
    phone: str = ""
    email: str = ""
    bank_name: str = ""
    bank_account: str = ""
    ifsc: str = ""
    einvoice_required: bool = False
    payment_terms_days: int = 30
    category: str = "general"


class Bank(Who):
    bank_name: str
    bank_account: str
    ifsc: str


class Status(Who):
    status: str


class NewPo(Who):
    vendor_id: str
    po_type: str = "goods"
    po_date: date
    lines: list[dict]


def _apply(request: Request, change):
    deps = ctx_of(request).deps
    if not deps.erp_dir:
        raise HTTPException(409, "The company records are read-only here.")
    try:
        out = change(deps)
    except records.RecordError as e:
        raise HTTPException(422, str(e)) from None
    deps.reload()  # the next invoice sees the change
    return out


@router.post("/vendors", status_code=201)
def add_vendor(request: Request, body: NewVendor):
    vid = _apply(request, lambda d: records.add_vendor(d.erp_dir, d.store, **body.model_dump()))
    return J({"vendor_id": vid}, 201)


@router.post("/vendors/{vendor_id}/bank")
def change_bank(request: Request, vendor_id: str, body: Bank):
    _apply(request, lambda d: records.change_bank(d.erp_dir, d.store, vendor_id, **body.model_dump()))
    return J({"ok": True})


@router.post("/vendors/{vendor_id}/status")
def set_status(request: Request, vendor_id: str, body: Status):
    _apply(request, lambda d: records.set_vendor_status(d.erp_dir, d.store, vendor_id, body.status,
                                                        actor=body.actor, why=body.why))
    return J({"ok": True})


@router.post("/pos", status_code=201)
def raise_po(request: Request, body: NewPo):
    po = _apply(request, lambda d: records.raise_po(d.erp_dir, d.store, **body.model_dump()))
    return J({"po_number": po}, 201)


@router.get("/record-changes")
def record_changes(request: Request, ref: str | None = None):
    return J(ctx_of(request).deps.store.record_changes(ref))

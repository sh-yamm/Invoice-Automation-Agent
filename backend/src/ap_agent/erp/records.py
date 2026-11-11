"""Changes people make to the company records: the approved-vendor list and purchase orders.

These are human controls. The agent reads the records and flags vendor problems, but it never calls these
functions: adding a vendor, changing a bank account or blocking a vendor is a classic fraud route, and raising
a PO is a business decision. Every change asks why and is logged with who, why and when.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ap_agent.rules.india.gstin import is_valid_gstin

VENDOR_COLS = ["vendor_id", "name", "gstin", "state_code", "address", "phone", "email", "bank_name", "bank_account",
               "ifsc", "einvoice_required", "gst_status", "payment_terms_days", "status", "category"]
PO_COLS = ["po_number", "vendor_id", "po_type", "po_date", "status", "line_no", "item_code", "description", "hsn_sac",
           "qty", "unit", "rate", "gst_rate"]


class RecordError(ValueError):
    """A change that is refused, with the reason a person can act on."""


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _need_why(why: str) -> str:
    if not (why or "").strip():
        raise RecordError("Say why: every change to the records is kept with who made it and why.")
    return why.strip()


def _vendor_rows(erp_dir: Path, vendor_id: str) -> tuple[list[dict], dict]:
    rows = _rows(erp_dir / "vendors.csv")
    row = next((r for r in rows if r["vendor_id"] == vendor_id), None)
    if row is None:
        raise RecordError(f"There is no vendor {vendor_id}.")
    return rows, row


def add_vendor(erp_dir: Path, store, *, name: str, gstin: str, address: str, phone: str, email: str, bank_name: str,
               bank_account: str, ifsc: str, einvoice_required: bool, payment_terms_days: int, category: str,
               actor: str, why: str) -> str:
    why = _need_why(why)
    gstin = (gstin or "").strip().upper()
    if not is_valid_gstin(gstin):
        raise RecordError(f"{gstin or 'That'} is not a valid GSTIN (the check digit does not match).")
    if not (name or "").strip():
        raise RecordError("Give the vendor's name.")
    rows = _rows(erp_dir / "vendors.csv")
    if any(r["gstin"] == gstin for r in rows):
        raise RecordError(f"A vendor with GSTIN {gstin} is already on the list.")
    vid = f"V{max((int(r['vendor_id'][1:]) for r in rows), default=0) + 1:03d}"
    row = {"vendor_id": vid, "name": name.strip(), "gstin": gstin, "state_code": gstin[:2], "address": address,
           "phone": phone, "email": email, "bank_name": bank_name, "bank_account": bank_account, "ifsc": ifsc,
           "einvoice_required": str(bool(einvoice_required)).lower(), "gst_status": "active",
           "payment_terms_days": str(int(payment_terms_days)), "status": "active", "category": category}
    _write(erp_dir / "vendors.csv", VENDOR_COLS, rows + [row])
    store.add_record_change("vendor_added", vid, actor, why, {k: row[k] for k in ("name", "gstin", "category")})
    return vid


def change_bank(erp_dir: Path, store, vendor_id: str, *, bank_name: str, bank_account: str, ifsc: str, actor: str,
                why: str) -> None:
    why = _need_why(why)
    rows, row = _vendor_rows(erp_dir, vendor_id)
    before = {k: row[k] for k in ("bank_name", "bank_account", "ifsc")}
    row.update(bank_name=bank_name, bank_account=bank_account, ifsc=ifsc)
    _write(erp_dir / "vendors.csv", VENDOR_COLS, rows)
    store.add_record_change("bank_changed", vendor_id, actor, why,
                            {"before": before, "after": {"bank_name": bank_name, "bank_account": bank_account, "ifsc": ifsc}})


def set_vendor_status(erp_dir: Path, store, vendor_id: str, status: str, *, actor: str, why: str) -> None:
    why = _need_why(why)
    if status not in ("active", "blocked"):
        raise RecordError("A vendor is either active (approved) or blocked.")
    rows, row = _vendor_rows(erp_dir, vendor_id)
    row["status"] = status
    _write(erp_dir / "vendors.csv", VENDOR_COLS, rows)
    store.add_record_change("vendor_approved" if status == "active" else "vendor_blocked", vendor_id, actor, why, {})


def _num(v, what: str) -> Decimal:
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise RecordError(f"{what} must be a number.") from None
    if d <= 0 and what != "GST %":
        raise RecordError(f"{what} must be more than zero.")
    return d


def raise_po(erp_dir: Path, store, *, vendor_id: str, po_type: str, po_date: date, lines: list[dict], actor: str,
             why: str) -> str:
    why = _need_why(why)
    _, vendor = _vendor_rows(erp_dir, vendor_id)
    if vendor["status"] != "active":
        raise RecordError(f"{vendor['name']} is blocked: approve the vendor before raising a PO.")
    if po_type not in ("goods", "services"):
        raise RecordError("A PO is for goods or for services.")
    lines = [l for l in lines if (l.get("description") or "").strip()]
    if not lines:
        raise RecordError("Add at least one line to the PO.")
    rows = _rows(erp_dir / "purchase_orders.csv")
    number = max((int(re.sub(r"\D", "", r["po_number"])) for r in rows), default=4600) + 1
    po = f"PO-{number}"
    new = []
    for i, l in enumerate(lines, start=1):
        new.append({"po_number": po, "vendor_id": vendor_id, "po_type": po_type, "po_date": po_date.isoformat(),
                    "status": "open", "line_no": i, "item_code": f"{po}-L{i}", "description": l["description"].strip(),
                    "hsn_sac": str(l.get("hsn_sac") or "").strip(), "qty": _num(l.get("qty"), "Quantity"),
                    "unit": str(l.get("unit") or "Nos").strip(), "rate": _num(l.get("rate"), "Rate"),
                    "gst_rate": _num(l.get("gst_rate", 18), "GST %")})
    _write(erp_dir / "purchase_orders.csv", PO_COLS, rows + new)
    value = sum(r["qty"] * r["rate"] for r in new)
    store.add_record_change("po_raised", po, actor, why, {"vendor_id": vendor_id, "lines": len(new), "value": str(value)})
    return po

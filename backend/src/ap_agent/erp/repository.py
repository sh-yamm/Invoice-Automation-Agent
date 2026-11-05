"""Read-only lookups over the company's existing records (data/erp/*.csv)."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from ap_agent.core.models import (
    Contract, GlAccount, Grn, PoLine, PurchaseOrder, ServiceAccount, Vendor,
)


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(f)]


class Repository:
    def __init__(self, vendors, pos, grns, contracts, gl_accounts, service_accounts):
        self._vendors: dict[str, Vendor] = {v.vendor_id: v for v in vendors}
        self._by_gstin: dict[str, Vendor] = {v.gstin: v for v in vendors}
        self._pos: dict[str, PurchaseOrder] = {p.po_number: p for p in pos}
        self._grns: dict[tuple[str, int], list[Grn]] = defaultdict(list)
        for g in grns:
            self._grns[(g.po_number, g.line_no)].append(g)
        self._contracts: list[Contract] = contracts
        self._gl: list[GlAccount] = gl_accounts
        self._services: dict[tuple[str, str], ServiceAccount] = {
            (s.vendor_id, s.consumer_no): s for s in service_accounts
        }

    @classmethod
    def load(cls, data_dir: Path) -> "Repository":
        d = Path(data_dir)
        vendors = [Vendor(**{**r, "einvoice_required": r["einvoice_required"] == "true"})
                   for r in _rows(d / "vendors.csv")]
        grouped: dict[str, list[dict]] = defaultdict(list)
        for r in _rows(d / "purchase_orders.csv"):
            grouped[r["po_number"]].append(r)
        pos = []
        for number, rows in grouped.items():
            head = rows[0]
            pos.append(PurchaseOrder(
                po_number=number, vendor_id=head["vendor_id"], po_type=head["po_type"],
                po_date=head["po_date"], status=head["status"],
                lines=[PoLine(**{k: r[k] for k in PoLine.model_fields}) for r in rows],
            ))
        grns = [Grn(**r) for r in _rows(d / "goods_receipts.csv")]
        contracts = [Contract(**r) for r in _rows(d / "contracts.csv")]
        gl = [GlAccount(**r) for r in _rows(d / "chart_of_accounts.csv")]
        services = [ServiceAccount(**r) for r in _rows(d / "service_accounts.csv")]
        return cls(vendors, pos, grns, contracts, gl, services)

    # vendors
    def vendors(self) -> list[Vendor]:
        return list(self._vendors.values())

    def vendor(self, vendor_id: str) -> Vendor | None:
        return self._vendors.get(vendor_id)

    def vendor_by_gstin(self, gstin: str | None) -> Vendor | None:
        return self._by_gstin.get((gstin or "").strip().upper())

    # purchase orders and receipts
    def po(self, po_number: str | None) -> PurchaseOrder | None:
        return self._pos.get((po_number or "").strip().upper())

    def pos(self) -> list[PurchaseOrder]:
        return list(self._pos.values())

    def all_grns(self) -> list[Grn]:
        return [g for gs in self._grns.values() for g in gs]

    def contracts(self) -> list[Contract]:
        return list(self._contracts)

    def open_pos(self, vendor_id: str) -> list[PurchaseOrder]:
        return [p for p in self._pos.values() if p.vendor_id == vendor_id and p.status == "open"]

    def grns(self, po_number: str, line_no: int) -> list[Grn]:
        return list(self._grns.get((po_number, line_no), []))

    # contracts, GL, service accounts
    def contract_for(self, vendor_id: str, po_number: str | None) -> Contract | None:
        matches = [c for c in self._contracts if c.vendor_id == vendor_id]
        if po_number:
            matches = [c for c in matches if c.po_number == po_number] or matches
        return matches[0] if matches else None

    def gl_accounts(self) -> list[GlAccount]:
        return list(self._gl)

    def service_account(self, vendor_id: str, consumer_no: str | None) -> ServiceAccount | None:
        return self._services.get((vendor_id, (consumer_no or "").strip()))

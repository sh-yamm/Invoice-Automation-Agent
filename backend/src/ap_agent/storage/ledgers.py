"""Read views over the ledgers and past cases. Writes happen through Store."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ap_agent.core.models import Outcome
from ap_agent.storage.db import Db


@dataclass
class CaseSummary:
    case_id: str
    invoice_no: str | None
    invoice_no_norm: str | None
    invoice_date: date | None
    grand_total: Decimal | None
    line_texts: list[str]
    outcome: Outcome | None
    status: str
    period_start: date | None
    decided_at: str | None


def _d(v):
    return date.fromisoformat(v) if v else None


class Ledger:
    def __init__(self, db: Db):
        self.db = db

    def invoiced(self, po_number: str, line_no: int | None = None) -> tuple[Decimal, Decimal]:
        sql = "SELECT qty, amount FROM po_ledger WHERE po_number = ?"
        params: tuple = (po_number,)
        if line_no is not None:
            sql += " AND line_no = ?"
            params += (line_no,)
        rows = self.db.query(sql, params)
        return (sum((Decimal(r["qty"]) for r in rows), Decimal("0")),
                sum((Decimal(r["amount"]) for r in rows), Decimal("0")))

    def lines_for_case(self, case_id: str) -> set[tuple[str, int]]:
        """The PO lines a past case billed (only approved cases write the ledger)."""
        rows = self.db.query("SELECT po_number, line_no FROM po_ledger WHERE case_id = ?", (case_id,))
        return {(r["po_number"], r["line_no"]) for r in rows}

    def period_billed(self, contract_id: str, period_start: date, exclude_case: str | None = None) -> str | None:
        rows = self.db.query(
            "SELECT case_id FROM period_ledger WHERE contract_id = ? AND period_start = ? AND case_id != ?",
            (contract_id, period_start.isoformat(), exclude_case or ""))
        return rows[0]["case_id"] if rows else None


class History:
    def __init__(self, db: Db):
        self.db = db

    def cases_for_vendor(self, vendor_id: str, exclude_case: str) -> list[CaseSummary]:
        rows = self.db.query(
            "SELECT * FROM cases WHERE vendor_id = ? AND case_id != ? ORDER BY invoice_date", (vendor_id, exclude_case))
        return [CaseSummary(
            case_id=r["case_id"], invoice_no=r["invoice_no"], invoice_no_norm=r["invoice_no_norm"],
            invoice_date=_d(r["invoice_date"]),
            grand_total=Decimal(r["grand_total"]) if r["grand_total"] is not None else None,
            line_texts=json.loads(r["line_texts"] or "[]"),
            outcome=Outcome(r["outcome"]) if r["outcome"] is not None else None,
            status=r["status"], period_start=_d(r["period_start"]), decided_at=r["decided_at"],
        ) for r in rows]

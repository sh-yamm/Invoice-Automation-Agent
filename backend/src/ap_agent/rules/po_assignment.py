"""The purchase order a person uploaded an invoice to, against the one the invoice prints.

No PO printed: the invoice is read as being for the PO the person chose. The same PO printed: fine. A different
PO printed: the agent keeps what the invoice says and the case is held (PO_ASSIGNMENT_MISMATCH), because one of
the two is wrong and a person should say which.
"""
from __future__ import annotations

import re

from ap_agent.core.models import Invoice


def same_po(a: str | None, b: str | None) -> bool:
    da, db = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
    return bool(da) and da == db


def apply_assigned_po(invoice: Invoice, assigned: str | None) -> tuple[Invoice, str]:
    """Returns the invoice and how the two compare: "none", "assigned", "matches" or "mismatch"."""
    if not assigned:
        return invoice, "none"
    if not invoice.po_ref:
        inv = invoice.model_copy(deep=True)
        inv.po_ref = assigned
        inv.confidence["po_ref"] = 1.0
        return inv, "assigned"
    return invoice, "matches" if same_po(invoice.po_ref, assigned) else "mismatch"

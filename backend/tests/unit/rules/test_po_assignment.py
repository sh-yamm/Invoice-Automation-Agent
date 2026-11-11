"""The PO a person uploads an invoice to, against the PO the invoice prints."""
from ap_agent.core.models import Invoice
from ap_agent.rules.po_assignment import apply_assigned_po, same_po


def test_same_po_ignores_spacing_and_dashes():
    assert same_po("PO-4518", "PO 4518") and same_po("po4518", "PO-4518")
    assert not same_po("PO-4518", "PO-4501") and not same_po(None, "PO-4518")


def test_no_printed_po_takes_the_assigned_one():
    inv, how = apply_assigned_po(Invoice(po_ref=None), "PO-4507")
    assert how == "assigned" and inv.po_ref == "PO-4507"


def test_printed_po_that_agrees_or_differs():
    assert apply_assigned_po(Invoice(po_ref="PO 4501"), "PO-4501")[1] == "matches"
    inv, how = apply_assigned_po(Invoice(po_ref="PO-4501"), "PO-4518")
    assert how == "mismatch" and inv.po_ref == "PO-4501"


def test_nothing_assigned_changes_nothing():
    inv, how = apply_assigned_po(Invoice(po_ref=None), None)
    assert how == "none" and inv.po_ref is None

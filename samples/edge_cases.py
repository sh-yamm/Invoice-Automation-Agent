"""The edge cases we chose to build: realistic invoices where the happy path would get the decision wrong.

One definition, used by the API (/api/edge-cases), the app's Edge cases page and the README. Each one names the
demo invoice that shows it and the PO trail where its history is.
"""
from __future__ import annotations

EDGE_CASES = [
    {
        "sample": "S04",
        "title": "A split PO runs out of balance",
        "scenario": "Nimbus IT bills a blanket PO every month for its retainer. Each invoice is the usual amount, "
                    "but the PO only had money for so many months, and this one goes past what is left.",
        "why_hard": "Nothing on this invoice is wrong by itself: right vendor, right PO, right amount. Only the "
                    "PO's billing history shows the problem, and the happy path checks an invoice against its PO, "
                    "not against everything billed before it.",
        "agent_does": "Every approved invoice is written to the PO ledger. The next invoice is checked against what "
                      "is left, not the PO's full value, and this one is held with the ledger and the exact excess "
                      "shown, so Procurement can amend the PO or approve only the remainder.",
    },
    {
        "sample": "S03",
        "title": "The vendor's bank account has changed",
        "scenario": "A genuine vendor sends a genuine invoice for goods that arrived, but with new bank details "
                    "printed for payment. This is how most invoice fraud works: someone impersonates the vendor.",
        "why_hard": "Every match passes: vendor, PO, receipt, price and quantity. A checker that only asks "
                    "'does this invoice match the order?' approves it and pays the wrong account.",
        "agent_does": "It compares the bank account and IFSC with the vendor master. A mismatch is a locked hold: "
                      "it can never be approved automatically, and approving it anyway needs a written verification "
                      "note (call the vendor on the number already on file). Only a person can change bank details.",
    },
    {
        "sample": "S06",
        "title": "The same invoice, sent again with a new number",
        "scenario": "Sai Krishna Logistics resends an invoice that was already paid, renumbered from SKL-1043 to "
                    "SKL-1043-A with a date two days later.",
        "why_hard": "The invoice number is new, so a duplicate check on vendor and invoice number passes and the "
                    "company pays twice.",
        "agent_does": "It normalises invoice numbers and compares the vendor's recent invoices on number similarity, "
                      "amount, date and line items. Two or more matching signals hold it as a probable duplicate, "
                      "with the original linked.",
    },
    {
        "sample": "S14",
        "title": "One purchase, split to stay under the approval limit",
        "scenario": "Orbit Office Systems bills PO-4540 in three invoices in one week, each just under the ₹5 lakh "
                    "limit the agent may approve on its own.",
        "why_hard": "Each invoice is within the limit, so each would pass alone. Together they are well over it: "
                    "splitting is a classic way to avoid a finance controller's sign-off.",
        "agent_does": "It adds up the vendor's invoices within a 7-day window. When the total crosses the limit, the "
                      "invoice goes to the finance controller for sign-off on the total, with the other invoices "
                      "listed.",
    },
]

ALSO_HANDLED = [
    {"sample": "S05", "title": "The same month billed twice under a new invoice number"},
    {"sample": "S07", "title": "A vendor that must e-invoice sends no IRN: rejected, as only the vendor can fix it"},
    {"sample": "S08", "title": "A scanned invoice with no PO number: the agent works out the PO"},
    {"sample": "S12", "title": "Text in the invoice tells the AI to approve it"},
    {"sample": "S13", "title": "Hidden text in the PDF says a different amount from the page"},
    {"sample": "S15", "title": "A look-alike vendor name that isn't on the approved list"},
    {"sample": "S16", "title": "The amount in words doesn't match the figures"},
    {"sample": "S10", "title": "Furniture bought without a PO, where policy needs one"},
    {"sample": "S11", "title": "A proforma sent as if it were a tax invoice"},
]

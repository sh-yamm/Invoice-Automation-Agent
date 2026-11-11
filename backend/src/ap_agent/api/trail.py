"""The paper trail behind one invoice: the PO Sample Client issued, what the vendor delivered, earlier invoices on
the same order, this invoice, and what the agent and people did with it, in date order."""
from __future__ import annotations

import json
import re
from decimal import Decimal

from ap_agent.core.constants import OUTCOME_LABELS
from ap_agent.core.money import fmt_inr, to_money


def _po_number(case: dict, repo) -> str | None:
    for f in case.get("findings", []):
        if f.check in ("po_resolve", "contract_resolve", "po_vendor") and f.data.get("po"):
            return str(f.data["po"])
    inv = json.loads(case["invoice_json"]) if case.get("invoice_json") else {}
    ref = (inv.get("po_ref") or "").strip()
    if not ref:
        return None
    if repo.po(ref):
        return ref
    digits = re.sub(r"\D", "", ref)
    return f"PO-{digits}" if digits and repo.po(f"PO-{digits}") else None


def _qty(q: Decimal, unit: str | None = None) -> str:
    text = f"{q:,.0f}" if q == q.to_integral_value() else f"{q:,}"
    return f"{text} {unit}" if unit else text


def _day(ts: str | None) -> str | None:
    return ts[:10] if ts else None


def build_trail(case: dict, deps) -> dict:
    repo, store = deps.repo, deps.store
    cid = case["case_id"]
    inv = json.loads(case["invoice_json"]) if case.get("invoice_json") else None
    vendor = repo.vendor(case["vendor_id"]) if case.get("vendor_id") else None
    po_no = _po_number(case, repo)
    po = repo.po(po_no) if po_no else None
    vendor = vendor or (repo.vendor(po.vendor_id) if po else None)
    contract = repo.contract_for(vendor.vendor_id, po.po_number if po else None) if vendor else None

    grns, lines = [], []
    if po:
        for l in po.lines:
            got = repo.grns(po.po_number, l.line_no)
            grns += got
            before_qty, before_amt = Decimal("0"), Decimal("0")
            for r in store.db.query("SELECT qty, amount FROM po_ledger WHERE po_number = ? AND line_no = ? AND case_id != ?",
                                    (po.po_number, l.line_no, cid)):
                before_qty += Decimal(r["qty"])
                before_amt += Decimal(r["amount"])
            lines.append({**l.model_dump(mode="json"), "amount": to_money(l.qty * l.rate),
                          "received_qty": sum((g.accepted_qty for g in got), Decimal("0")) if got else None,
                          "received_date": max(g.received_date for g in got).isoformat() if got else None,
                          "billed_before_qty": before_qty, "billed_before_amount": to_money(before_amt)})

    earlier = []
    if po:
        rows = store.db.query("SELECT case_id, SUM(CAST(amount AS REAL)) AS amt FROM po_ledger WHERE po_number = ? "
                              "AND case_id != ? GROUP BY case_id", (po.po_number, cid))
        for r in rows:
            other = store.get_case(r["case_id"])
            if other:
                earlier.append({"case_id": other["case_id"], "invoice_no": other.get("invoice_no"),
                                "invoice_date": other.get("invoice_date"), "amount": to_money(Decimal(str(r["amt"]))),
                                "outcome": OUTCOME_LABELS[int(other["outcome"])] if other.get("outcome") is not None else None})
        earlier.sort(key=lambda e: e["invoice_date"] or "")

    steps = []
    if contract:
        steps.append({"kind": "contract", "date": contract.start_date.isoformat(), "who": "Sample Client",
                      "title": f"Contract {contract.contract_id} signed",
                      "detail": f"{contract.description}: {fmt_inr(contract.amount_per_period)} per {contract.billing_cycle.replace('ly', '')}, "
                                f"{contract.start_date:%d %b %Y} to {contract.end_date:%d %b %Y}"})
    if po:
        steps.append({"kind": "po", "date": po.po_date.isoformat(), "who": "Sample Client",
                      "title": f"Purchase order {po.po_number} issued",
                      "detail": (f"{_qty(po.lines[0].qty, po.lines[0].unit)} of {po.lines[0].description} at {fmt_inr(po.lines[0].rate)}"
                                 if len(po.lines) == 1 else f"{len(po.lines)} lines") + f", {fmt_inr(po.value)} before GST"})
    for g in sorted({g.grn_number: g for g in grns}.values(), key=lambda g: g.received_date):
        mine = [x for x in grns if x.grn_number == g.grn_number]
        units = {po.line(x.line_no).unit for x in mine if po.line(x.line_no)}
        qty = sum((x.accepted_qty for x in mine), Decimal("0"))
        what = _qty(qty, units.pop()) if len(units) == 1 else f"{len(mine)} lines"
        steps.append({"kind": "grn", "date": g.received_date.isoformat(), "who": vendor.name if vendor else "Vendor",
                      "title": f"Goods received, receipt {g.grn_number}",
                      "detail": f"Delivered by the vendor; the warehouse accepted {what}"})
    for e in earlier:
        steps.append({"kind": "earlier", "date": e["invoice_date"], "who": vendor.name if vendor else "Vendor",
                      "title": f"Earlier invoice {e['invoice_no']}", "detail": f"{fmt_inr(Decimal(str(e['amount'])))} billed on this order, {(e['outcome'] or '').lower()}",
                      "case_id": e["case_id"]})
    if inv:
        steps.append({"kind": "invoice", "date": inv.get("invoice_date") or _day(case["created_at"]),
                      "who": vendor.name if vendor else (inv.get("supplier_name") or "Vendor"),
                      "title": f"Invoice {inv.get('invoice_no') or ''} sent".replace("  ", " "),
                      "detail": f"{fmt_inr(Decimal(str(inv['grand_total'])))} including GST" if inv.get("grand_total") else ""})
    steps.append({"kind": "check", "date": _day(case["created_at"]), "who": "Agent", "title": "Checked by the agent",
                  "detail": f"{len(case.get('findings', []))} checks against the order, the receipt and the rulebook"})
    if case.get("outcome") is not None and case.get("decided_at"):
        steps.append({"kind": "decision", "date": _day(case["decided_at"]), "who": "Agent",
                      "title": f"Decision: {OUTCOME_LABELS[int(case['outcome'])]}", "detail": case.get("why") or ""})
    for h in case.get("human_actions", []):
        steps.append({"kind": "person", "date": _day(h.get("at")), "who": h.get("actor") or "A person",
                      "title": f"{(h.get('action') or '').replace('_', ' ').capitalize()}", "detail": h.get("note") or ""})
    order = {"contract": 0, "po": 1, "grn": 2, "earlier": 3, "invoice": 4, "check": 5, "decision": 6, "person": 7}
    steps.sort(key=lambda s: (order[s["kind"]] >= 5, s["date"] or "", order[s["kind"]]))

    return {
        "vendor": {"vendor_id": vendor.vendor_id, "name": vendor.name, "gstin": vendor.gstin, "category": vendor.category,
                   "bank": f"{vendor.bank_name} ····{str(vendor.bank_account)[-4:]}", "payment_terms_days": vendor.payment_terms_days,
                   "status": vendor.status} if vendor else None,
        "po": {"po_number": po.po_number, "po_date": po.po_date.isoformat(), "po_type": po.po_type, "status": po.status,
               "value": to_money(po.value), "lines": lines} if po else None,
        "grns": [g.model_dump(mode="json") for g in grns],
        "contract": contract.model_dump(mode="json") if contract else None,
        "earlier_invoices": earlier,
        "invoice": {"invoice_no": inv.get("invoice_no"), "invoice_date": inv.get("invoice_date"),
                    "grand_total": inv.get("grand_total"), "lines": inv.get("lines", [])} if inv else None,
        "steps": steps,
    }

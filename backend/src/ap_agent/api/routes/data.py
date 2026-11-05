"""Read-only views of the company's existing records, plus our PO ledger."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ap_agent.api.common import J, ctx_of
from ap_agent.core.money import to_money

router = APIRouter(prefix="/api/data")


@router.get("/{name}")
def data(request: Request, name: str):
    deps = ctx_of(request).deps
    repo = deps.repo
    if name == "vendors":
        return J([v.model_dump(mode="json") for v in repo.vendors()])
    if name == "purchase_orders":
        return J([{**l.model_dump(mode="json"), "vendor_id": p.vendor_id, "po_type": p.po_type,
                   "po_date": p.po_date.isoformat(), "status": p.status} for p in repo.pos() for l in p.lines])
    if name == "goods_receipts":
        return J([g.model_dump(mode="json") for g in repo.all_grns()])
    if name == "contracts":
        return J([c.model_dump(mode="json") for c in repo.contracts()])
    if name == "chart_of_accounts":
        return J([a.model_dump(mode="json") for a in repo.gl_accounts()])
    if name == "po_ledger":
        rows = []
        for p in repo.pos():
            invoiced = deps.store.ledger.invoiced(p.po_number)[1]
            v = repo.vendor(p.vendor_id)
            rows.append({"po_number": p.po_number, "vendor": v.name if v else p.vendor_id, "po_type": p.po_type,
                         "value": to_money(p.value), "invoiced": to_money(invoiced),
                         "remaining": to_money(max(p.value - invoiced, 0)),
                         "used_pct": round(float(invoiced / p.value * 100), 1) if p.value else 0.0})
        return J(rows)
    raise HTTPException(404, f"No data set called '{name}'.")

"""Dashboard numbers, computed from the case records (never hard-coded)."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Request

from ap_agent.api.common import J, ctx_of
from ap_agent.core.models import Outcome
from samples.specs import SPECS

router = APIRouter(prefix="/api")
PROTECTED = {"BANK_DETAILS_MISMATCH", "DUPLICATE_EXACT", "DUPLICATE_PROBABLE", "LOOKALIKE_VENDOR",
             "SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT", "TEXT_LAYER_MISMATCH", "VENDOR_NOT_APPROVED"}


def _dt(s):
    return datetime.fromisoformat(s) if s else None


@router.get("/kpis")
def kpis(request: Request):
    cases = [c for c in ctx_of(request).deps.store.list_cases({}) if c["outcome"] is not None]
    touchless = [c for c in cases if c["outcome"] is Outcome.APPROVED and c["primary_code"] == "ALL_CHECKS_PASSED"]
    money = lambda cs: sum((Decimal(c["grand_total"]) for c in cs if c["grand_total"]), Decimal("0"))
    handled = [(_dt(c["decided_at"]) - _dt(c["created_at"])).total_seconds() for c in cases
               if c["decided_at"] and c["created_at"]]
    latest = max((_dt(c["created_at"]) for c in cases), default=datetime.now()).date()
    series = []
    for i in range(6, -1, -1):
        day = latest - timedelta(days=i)
        today = [c for c in cases if _dt(c["created_at"]).date() == day]
        auto = [c for c in today if c in touchless]
        series.append({"date": day.isoformat(), "cases": len(today),
                       "touchless_pct": round(100 * len(auto) / len(today), 1) if today else None})
    return J({
        "processed": len(cases),
        "total_inr": money(cases),
        "touchless": len(touchless),
        "touchless_pct": round(100 * len(touchless) / len(cases), 1) if cases else 0.0,
        "exceptions": len(cases) - len(touchless),
        "protected_inr": money([c for c in cases if c["primary_code"] in PROTECTED]),
        "protected_cases": sum(1 for c in cases if c["primary_code"] in PROTECTED),
        "avg_handling_seconds": round(sum(handled) / len(handled), 1) if handled else None,
        "outcomes": {o.name.lower(): sum(1 for c in cases if c["outcome"] is o) for o in Outcome},
        "by_type": {t: sum(1 for c in cases if c["txn_type"] == t) for t in ("standard_po", "recurring", "po_less")},
        "touchless_series": series,
    })


@router.get("/samples")
def samples(request: Request):
    return J([{"id": s.id, "title": s.title, "blurb": s.blurb, "layout": s.layout, "scanned": s.scanned,
               "vendor": s.supplier["name"], "total": s.invoice.grand_total,
               "expected_outcome": int(s.expected_outcome), "expected_code": s.expected_code}
              for s in SPECS.values()])

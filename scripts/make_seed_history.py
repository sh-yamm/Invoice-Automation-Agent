"""Generate data/seed/history.json: past cases and ledger rows loaded on every demo reset.

Run from the repo root:  py -3.11 scripts/make_seed_history.py
"""
import json
import random
import sys
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from ap_agent.rules.normalise import normal_invoice_no  # noqa: E402

OUT = ROOT / "data" / "seed" / "history.json"
rng = random.Random(42)


def money(x) -> str:
    return str(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def case(case_id, vendor_id, vendor_name, invoice_no, _norm, inv_date, taxable, gst_pct, lines, txn_type,
         outcome="APPROVED", code="ALL_CHECKS_PASSED", ledger=None, period=None, handling_s=None,
         owner="No one, handled automatically", why="Every required check passed.", status=None):
    total = Decimal(taxable) * (1 + Decimal(gst_pct) / 100)
    created = datetime.combine(inv_date + timedelta(days=rng.randint(1, 3)), datetime.min.time()) + timedelta(
        hours=rng.randint(9, 17), minutes=rng.randint(0, 59))
    decided = created + timedelta(seconds=handling_s or rng.randint(24, 55))
    return {
        "case_id": case_id, "vendor_id": vendor_id, "vendor_name": vendor_name,
        "invoice_no": invoice_no, "invoice_no_norm": normal_invoice_no(invoice_no), "invoice_date": inv_date.isoformat(),
        "grand_total": money(total), "line_texts": lines, "txn_type": txn_type,
        "outcome": outcome, "primary_code": code, "owner": owner, "why": why, "status": status,
        "created_at": created.isoformat(timespec="seconds"), "decided_at": decided.isoformat(timespec="seconds"),
        "ledger": ledger or [], "period": period,
    }


cases = []

# Nimbus IT retainer, Jun–Oct 2026: ₹6,00,000 of the ₹6,60,000 blanket PO-4490 already billed.
for i, (num, month) in enumerate([("080", 6), ("082", 7), ("084", 8), ("086", 9), ("088", 10)]):
    start = date(2026, month, 1)
    cases.append(case(f"H-NIT-{month:02d}", "V003", "Nimbus IT Services LLP", f"NIT/26-27/{num}", f"NIT2627{num}",
                      start + timedelta(days=1), 120000, 18, ["IT support retainer"], "recurring",
                      ledger=[{"po_number": "PO-4490", "line_no": 1, "qty": "0", "amount": "120000"}],
                      period={"contract_id": "CT-901", "period_start": start.isoformat()}))

# The original Sai Krishna freight invoice that S06 resends.
cases.append(case("H-SKL-1043", "V006", "Sai Krishna Logistics", "SKL-1043", "SKL1043", date(2026, 10, 24),
                  55500, 5, ["Freight Bengaluru to Chennai, 32 ft trailer"], "standard_po",
                  ledger=[{"po_number": "PO-4475", "line_no": 1, "qty": "3", "amount": "55500"}]))

# Orbit Office Systems: two ₹4,89,700 invoices this week, each under the ₹5 L limit (S14 is the third).
for i, (num, d) in enumerate([("0211", date(2026, 11, 2)), ("0214", date(2026, 11, 3))], start=1):
    cases.append(case(f"H-ORB-{num}", "V008", "Orbit Office Systems", f"ORB/26-27/{num}", f"ORB2627{num.lstrip('0')}",
                      d, 415000, 18, [f"Workstation set, phase {i}"], "standard_po",
                      ledger=[{"po_number": "PO-4540", "line_no": i, "qty": "1", "amount": "415000"}]))

# Namma Power electricity bills, May–Oct 2026: the baseline for the amount-anomaly check.
for month, taxable in [(5, 14576), (6, 15339), (7, 16186), (8, 15805), (9, 15169), (10, 15593)]:
    cases.append(case(f"H-NPD-{month:02d}", "V007", "Namma Power Distribution Ltd", f"NPD/KA/26{month:02d}-48213",
                      f"NPDKA26{month:02d}48213", date(2026, month, 28), taxable, 18,
                      ["Electricity charges, Bellandur HQ"], "po_less",
                      ledger=[], period=None))

# Older cases across vendors, Aug–Sep 2026, so the dashboard has history. Dates are kept well away from the
# demo samples so they never look like duplicates of them.
pool = [
    ("V001", "Shree Ganesh Office Furniture", "SGOF/26-27/03", ["Visitor chair", "Storage locker"]),
    ("V002", "Kaveri Packaging Industries", "KPI/26-27/10", ["Shrink wrap roll", "Carton sealing tape"]),
    ("V004", "Deccan Steel Traders", "DST/2627/07", ["MS flat bar 40x6 mm"]),
    ("V005", "Mehta Electricals Pvt Ltd", "ME/26-27/19", ["Distribution board 12-way", "Copper cable 4 sq mm"]),
    ("V006", "Sai Krishna Logistics", "SKL-09", ["Freight Bengaluru to Hyderabad, 20 ft"]),
]
holds = [("ON_HOLD", "PRICE_VARIANCE", "Procurement"), ("ON_HOLD", "RECEIPT_MISSING", "Warehouse"),
         ("ON_HOLD", "UNEXPECTED_CHARGES", "Procurement"), ("REJECTED", "MISSING_MANDATORY_FIELD", "Vendor")]
for i in range(24):
    vid, name, prefix, items = pool[i % len(pool)]
    d = date(2026, 8, 3) + timedelta(days=i * 2)
    num = f"{prefix}{i + 10:02d}"
    norm = num.replace("/", "").replace("-", "").upper()
    taxable = rng.randrange(18000, 380000, 500)
    if i % 6 == 5:
        o, code, owner = holds[(i // 6) % len(holds)]
        cases.append(case(f"H-OLD-{i:02d}", vid, name, num, norm, d, taxable, 18, [items[i % len(items)]],
                          "standard_po", outcome=o, code=code, owner=owner, why="Held for review.",
                          status="done" if o == "REJECTED" else "waiting", handling_s=rng.randint(30, 70)))
    else:
        cases.append(case(f"H-OLD-{i:02d}", vid, name, num, norm, d, taxable, 18, [items[i % len(items)]],
                          "standard_po"))

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"cases": cases}, indent=1), encoding="utf-8")
print(f"wrote {len(cases)} cases to {OUT}")

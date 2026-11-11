"""The 38 past invoices behind the demo: real documents, run through the real agent once.

Each one is a printed invoice (same generator as the demo samples) tied to a real purchase order and goods
receipt in Sample Client's records, so every past case has the full paper trail: PO -> receipt -> invoice -> checks ->
decision. scripts/build_history.py runs them through the pipeline in date order and saves the result as the
starting history (data/seed/history.db + data/seed/files).

Amounts, invoice numbers and dates are the ones the dashboard has always shown, so the demo samples' checks
(duplicates, amount history, PO balances) see the same history as before.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from ap_agent.core.models import Outcome
from samples.specs import SUPPLIERS, SampleSpec, _invoice

ROOT = Path(__file__).resolve().parents[1]
LEGACY = json.loads((ROOT / "data" / "seed" / "history.json").read_text(encoding="utf-8"))["cases"]
_OLD = {c["case_id"]: c for c in LEGACY}


@dataclass
class HistoryCase:
    case_id: str
    created_at: datetime
    spec: SampleSpec
    po_status_after: str = "closed"   # the PO's status once this invoice is settled (held ones stay open)
    also_ok: tuple = ()                # other (outcome, code) results that are the right call too
    human: dict | None = None          # what a person did with it afterwards (action, actor, note, hours later)


@dataclass
class PoLine:
    po_number: str
    vendor_id: str
    po_type: str
    po_date: date
    status: str
    line_no: int
    item_code: str
    description: str
    hsn_sac: str
    qty: D
    unit: str
    rate: D
    gst_rate: str


@dataclass
class Grn:
    grn_number: str
    po_number: str
    line_no: int
    qty: D
    received_date: date


SUP = {"V001": "sgof", "V002": "kaveri", "V003": "nimbus", "V004": "deccan", "V005": "mehta", "V006": "skl",
       "V007": "fibernet", "V008": "orbit"}
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

# item -> (code, HSN/SAC, unit, typical rate, GST %, goods?)
ITEMS = {
    "Visitor chair": ("FUR-VCH-02", "9401", "Nos", "3800", "18", True),
    "Storage locker": ("FUR-LKR-06", "9403", "Nos", "7800", "18", True),
    "Shrink wrap roll": ("PKG-SWR-23", "3920", "Rolls", "1450", "18", True),
    "Carton sealing tape": ("PKG-TAP-48", "3919", "Rolls", "96", "18", True),
    "MS flat bar 40x6 mm": ("STL-FLT-40", "7216", "kg", "62", "18", True),
    "Distribution board 12-way": ("ELE-DB-12", "8537", "Nos", "6800", "18", True),
    "Copper cable 4 sq mm": ("ELE-CU-04", "8544", "m", "92", "18", True),
    "Freight Bengaluru to Hyderabad, 20 ft": ("LOG-FRT-20", "996511", "Trips", "14500", "5", False),
}


def split(taxable: D, nominal: D) -> tuple[D, D]:
    """A whole quantity and a rate (in paise) whose product is exactly `taxable`, near the nominal rate."""
    guess = max(1, int(taxable / nominal))
    for step in range(0, guess + 1):
        for q in (guess + step, guess - step):
            if q >= 1 and (taxable * 100) % q == 0:
                rate = taxable / q
                if rate == rate.quantize(D("0.01")):
                    return D(q), rate.quantize(D("0.01"))
    return D(1), taxable


def _irn(no: str) -> str:
    return hashlib.sha256(no.encode()).hexdigest()


def _created(cid: str) -> datetime:
    return datetime.fromisoformat(_OLD[cid]["created_at"])


def build() -> tuple[list[HistoryCase], list[PoLine], list[Grn]]:
    cases: list[HistoryCase] = []
    pos: list[PoLine] = []
    grns: list[Grn] = []

    # Nimbus IT retainer, Jun-Oct, on the blanket PO-4490 / contract CT-901.
    n = SUPPLIERS["nimbus"]
    for num, m in [("080", 6), ("082", 7), ("084", 8), ("086", 9), ("088", 10)]:
        start = date(2026, m, 1)
        end = (date(2026, m + 1, 1) - timedelta(days=1))
        inv = _invoice(n, f"NIT/26-27/{num}", start + timedelta(days=1), "PO-4490",
                       [(f"IT support retainer, {MONTHS[m]} 2026", "998313", "1", "Month", "120000")],
                       period_start=start, period_end=end)
        cid = f"H-NIT-{m:02d}"
        cases.append(HistoryCase(cid, _created(cid), SampleSpec(cid, "", "", "modern", n, inv, Outcome.APPROVED,
                                                                "ALL_CHECKS_PASSED"), "open"))

    # The Sai Krishna freight invoice that demo S06 resends.
    sk = SUPPLIERS["skl"]
    inv = _invoice(sk, "SKL-1043", date(2026, 10, 24), "PO-4475",
                   [("Freight Bengaluru to Chennai, 32 ft trailer", "996511", "3", "Trips", "18500")], gst="5")
    cases.append(HistoryCase("H-SKL-1043", _created("H-SKL-1043"),
                             SampleSpec("H-SKL-1043", "", "", "compact", sk, inv, Outcome.APPROVED, "ALL_CHECKS_PASSED"),
                             "open"))

    # Orbit Office Systems: phases 1 and 2 of PO-4540 (demo S14 is phase 3).
    o = SUPPLIERS["orbit"]
    for i, (num, d) in enumerate([("0211", date(2026, 11, 2)), ("0214", date(2026, 11, 3))], start=1):
        inv = _invoice(o, f"ORB/26-27/{num}", d, "PO-4540", [(f"Workstation set, phase {i}", "9403", "1", "Set", "415000")])
        cid = f"H-ORB-{num}"
        if i == 1:
            cases.append(HistoryCase(cid, _created(cid), SampleSpec(cid, "", "", "classic", o, inv, Outcome.APPROVED,
                                                                    "ALL_CHECKS_PASSED"), "open"))
        else:
            # The second phase within 7 days: together over the Rs 5 L limit, so the agent flags a possible split.
            # The finance controller checked that phase 2 was delivered on its own receipt and approved it.
            cases.append(HistoryCase(
                cid, _created(cid), SampleSpec(cid, "", "", "classic", o, inv, Outcome.NEEDS_SIGNOFF, "SPLIT_BELOW_LIMIT"),
                "open", also_ok=((Outcome.ON_HOLD, "AGENT_ESCALATION"),),
                human={"actor": "Finance controller", "hours": 3,
                       "note": "Phase 2 of PO-4540, delivered on its own receipt (GRN-7771). Not a split; approved."}))

    # Namma Fibernet leased line: each bill dated the 1st, for the month before (demo S09 is October's).
    f = SUPPLIERS["fibernet"]
    for m, taxable in [(5, 14576), (6, 15339), (7, 16186), (8, 15805), (9, 15169), (10, 15593)]:
        prev = m - 1
        inv = _invoice(f, f"NF/BLR/26{m:02d}-48213", date(2026, m, 1), None,
                       [(f"Internet leased line 100 Mbps, {MONTHS[prev]} 2026", "998422", "1", "Month", str(taxable))],
                       consumer_no="NF-BLR-0048213", period_start=date(2026, prev, 1),
                       period_end=date(2026, m, 1) - timedelta(days=1))
        cid = f"H-NF-{m:02d}"
        created = datetime.combine(date(2026, m, 2), datetime.min.time()) + timedelta(hours=10, minutes=5 * m)
        cases.append(HistoryCase(cid, created, SampleSpec(cid, "", "", "compact", f, inv, Outcome.APPROVED,
                                                          "ALL_CHECKS_PASSED")))

    # Older purchase-order invoices across vendors, Aug-Sep. Each has its own PO and goods receipt.
    for i in range(24):
        cid = f"H-OLD-{i:02d}"
        old = _OLD[cid]
        vid, item = old["vendor_id"], old["line_texts"][0]
        sup = SUPPLIERS[SUP[vid]]
        code, hsn, unit, nominal, gst, goods = ITEMS[item]
        inv_date = date.fromisoformat(old["invoice_date"])
        taxable = (D(old["grand_total"]) / D("1.18")).quantize(D("1"))
        po_no, grn_no = f"PO-{4301 + i}", f"GRN-{7601 + i}"
        outcome, primary = Outcome[old["outcome"]], old["primary_code"]
        extra = None
        if primary == "UNEXPECTED_CHARGES":  # loading charges that were never on the PO
            extra = max(D(500), (taxable * D("0.03") / 500).quantize(D("1")) * 500)
            qty, rate = split(taxable - extra, D(nominal))
        else:
            qty, rate = split(taxable, D(nominal))
        po_rate = (rate / D("1.05")).quantize(D("0.01")) if primary == "PRICE_VARIANCE" else rate
        lines = [(item, hsn, str(qty), unit, str(rate))]
        if extra:
            lines.append(("Loading and unloading charges", "996719", "1", "Lot", str(extra)))
        kw = {}
        if vid == "V005":
            kw.update(irn=_irn(old["invoice_no"]), has_qr=True)
        inv = _invoice(sup, old["invoice_no"], inv_date, po_no, lines, gst=gst, **kw)
        if primary == "MISSING_MANDATORY_FIELD":  # the buyer's GSTIN was left off the invoice
            inv = inv.model_copy(update={"buyer_gstin": None})
        pos.append(PoLine(po_no, vid, "goods" if goods else "services", inv_date - timedelta(days=14), "open", 1, code,
                          item, hsn, qty, unit, po_rate, gst))
        if goods and primary != "RECEIPT_MISSING":
            grns.append(Grn(grn_no, po_no, 1, qty, inv_date - timedelta(days=3)))
        settled = outcome is Outcome.APPROVED
        layout = ["classic", "modern", "compact"][i % 3]
        cases.append(HistoryCase(cid, _created(cid), SampleSpec(cid, "", "", layout, sup, inv, outcome, primary),
                                 "closed" if settled else "open"))

    cases.sort(key=lambda c: c.created_at)
    return cases, pos, grns


HISTORY, HISTORY_POS, HISTORY_GRNS = build()

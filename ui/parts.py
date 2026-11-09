"""HTML pieces shared by the pages: money and dates, stage tiles, the paper trail, the match table, the check log."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape as h

OUTCOME = {0: ("approved", "Approved", "✓"), 1: ("signoff", "Needs sign-off", "✎"), 2: ("hold", "On hold", "!"),
           3: ("reject", "Rejected", "✕")}
TXN = {"standard_po": "Standard PO", "recurring": "Recurring", "po_less": "PO-less"}


def num(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal(0)


def inr(v, places: int = 2) -> str:
    if v is None or v == "":
        return "—"
    d = num(v).quantize(Decimal(1) if places == 0 else Decimal("0.01"))
    neg, d = d < 0, abs(d)
    whole, _, frac = f"{d:.{places}f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    s = ",".join(groups + [tail]) if groups else tail
    return f"{'-' if neg else ''}₹{s}{'.' + frac if places else ''}"


def lakh(v) -> str:
    d = num(v)
    if d >= 10_000_000:
        return f"₹{d / 10_000_000:.2f} Cr"
    if d >= 100_000:
        return f"₹{d / 100_000:.2f} L"
    return inr(d, 0)


def day(iso) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(iso)


def ago(iso) -> str:
    if not iso:
        return ""
    s = (datetime.now() - datetime.fromisoformat(str(iso)[:19])).total_seconds()
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} d ago"


def chip(outcome, status) -> str:
    if status == "running" or outcome is None:
        return '<span class="st-chip running">● Reading</span>'
    cls, label, icon = OUTCOME[int(outcome)]
    return f'<span class="st-chip {cls}">{icon} {label}</span>'


def hero(eyebrow: str, title: str, body: str = "", chips: list[tuple[str, str]] | None = None) -> str:
    c = "".join(f'<span class="chip">{h(k)} <b>{h(v)}</b></span>' for k, v in (chips or []))
    return (f'<div class="hero"><p class="eyebrow">{h(eyebrow)}</p><h1>{h(title)}</h1>'
            f'{f"<p>{h(body)}</p>" if body else ""}{f"<div class=chips>{c}</div>" if c else ""}</div>')


# ---------- stage tiles (the live run view) ----------

RAIL = [
    ("Receive", "file · pages", ["ingest", "render", "parse"], ["ingest"]),
    ("Read", "fields · tamper", ["reconcile", "extract", "ground"], ["reconcile", "read"]),
    ("Classify", "document · type", ["classify_document", "classify_transaction"], ["classify"]),
    ("Validate", "GST rules", ["validate"], ["validate"]),
    ("Match", "", ["standard_po", "recurring", "po_less"], ["match"]),
    ("Controls", "fraud · duplicates", ["controls"], ["controls"]),
    ("Decide", "rules + agent", ["completeness_guard", "decide", "human_gate", "finalise"], ["decide", "human", "finalise"]),
]
MATCH = {"standard_po": ("Match", "PO · receipt"), "recurring": ("Contract", "period · balance"),
         "po_less": ("Code & route", "policy · GL")}


def rail_index(stage: str) -> int:
    return next((i for i, r in enumerate(RAIL) if stage in r[3]), 6)


def stage_tiles(events: list[dict], findings: list[dict], txn_type, running: bool) -> str:
    started = {str(e["payload"].get("node")) for e in events if e["type"] == "node_started"}
    finished = {str(e["payload"].get("node")) for e in events if e["type"] == "node_finished"}
    out = []
    for i, (label, sub, nodes, _) in enumerate(RAIL):
        fs = [f for f in findings if rail_index(f["stage"]) == i]
        fail = any(f["status"] == "fail" for f in fs)
        reject = any(f["status"] == "fail" and f.get("outcome") == 3 for f in fs)
        touched = any(n in started for n in nodes) or bool(fs)
        active = running and any(n in started and n not in finished for n in nodes)
        state = "active" if active else "fail" if reject else "warn" if fail else "done" if touched else ""
        if label == "Match" and txn_type in MATCH:
            label, sub = MATCH[txn_type]
        out.append(f'<li class="stage {state}"><span class="n">{i + 1:02d}</span><span class="nm">{h(label)}</span>'
                   f'<span class="t">{h(sub)}</span></li>')
    return f'<ol class="rail" aria-label="Pipeline stages">{"".join(out)}</ol>'


# ---------- paper trail ----------

LANES = [("Zentra Retail", "the buyer", {"contract", "po", "grn"}), ("Vendor", "the seller", {"earlier", "invoice"}),
         ("Agent and people", "accounts payable", {"check", "decision", "person"})]
ICON = {"contract": "✍", "po": "▤", "grn": "⬇", "earlier": "↺", "invoice": "₹", "check": "✓", "decision": "⚖", "person": "◉"}


def paper_trail(trail: dict) -> str:
    steps = trail.get("steps") or []
    if len(steps) < 2:
        return ""
    cols = f"minmax(96px,.5fr) repeat({len(steps)}, minmax(136px,1fr))"
    cells = ['<div></div>']
    for i, s in enumerate(steps):
        agent = " agent" if s["kind"] in ("check", "decision", "person") else ""
        cells.append(f'<div class="ax{agent}" style="grid-column:{i + 2};grid-row:1"><span class="n">{i + 1}</span>'
                     f'<span class="d">{day(s.get("date"))}</span></div>')
    for r, (name, sub, kinds) in enumerate(LANES):
        cells.append(f'<div class="lane" style="grid-row:{r + 2}"><b>{name}</b><span>{sub}</span></div>')
        for i, s in enumerate(steps):
            if s["kind"] not in kinds:
                continue
            cls = "agent" if r == 2 else "vendor" if r == 1 else ""
            title = h(s["title"])
            if s.get("case_id"):
                title = f'<a href="case?id={h(s["case_id"])}" target="_self">{title}</a>'
            cells.append(f'<div class="step {cls}" style="grid-column:{i + 2};grid-row:{r + 2}">'
                         f'<span class="ic">{ICON[s["kind"]]}</span><div><div class="st">{title}</div>'
                         f'<div class="sd">{h(s.get("detail") or "")}</div></div></div>')
    return (f'<section class="trail" aria-label="Paper trail"><div class="h3">How this invoice got here</div>'
            f'<div class="note">Every document in the chain, in date order: what Zentra ordered, what the vendor '
            f'delivered and billed, and what happened next.</div>'
            f'<div class="tgrid" style="grid-template-columns:{cols}">{"".join(cells)}</div></section>')


# ---------- ordered / received / billed ----------

def _qty(v, unit=None) -> str:
    if v in (None, ""):
        return "—"
    d = num(v)
    s = f"{d:,.0f}" if d == d.to_integral_value() else f"{d:,}"
    return f"{s} {unit}" if unit else s


def match_table(trail: dict) -> str:
    po, inv = trail.get("po"), trail.get("invoice")
    if not po or not inv:
        return ""
    services = po["po_type"] != "goods"
    lines = inv.get("lines") or []
    rows = []
    for i, pl in enumerate(po["lines"]):
        il = next((l for l in lines if l.get("hsn_sac") and l.get("hsn_sac") == pl["hsn_sac"]), None)
        if il is None and len(lines) == len(po["lines"]):
            il = lines[i]
        rec = "" if services else (
            f'<td class="r">{"<span class=bad>Nothing yet</span>" if pl["received_qty"] is None else _qty(pl["received_qty"], pl["unit"])}'
            f'<div class="sub">{day(pl["received_date"]) if pl["received_date"] else "no receipt"}</div></td>')
        before = num(pl["billed_before_amount"])
        if il:
            up = num(il["rate"]) > num(pl["rate"])
            over = (pl["received_qty"] is not None and num(il["qty"]) > num(pl["received_qty"])) or \
                   num(il["qty"]) + num(pl["billed_before_qty"]) > num(pl["qty"])
            pct = f", {(num(il['rate']) - num(pl['rate'])) / num(pl['rate']) * 100:.1f}% above the PO" if up else ""
            this = (f'<span class="{"bad" if over else ""}">{_qty(il["qty"], il.get("unit"))}</span>'
                    f'<div class="sub {"bad" if up else ""}">at {inr(il["rate"])}{pct}</div>')
        else:
            this = '<span class="muted">not on this invoice</span>'
        rows.append(f'<tr><td>{h(pl["description"])}<div class="sub mono">{h(pl["item_code"])}, HSN/SAC {h(pl["hsn_sac"])}</div></td>'
                    f'<td class="r">{_qty(pl["qty"], pl["unit"])}<div class="sub">at {inr(pl["rate"])}</div></td>{rec}'
                    f'<td class="r">{_qty(pl["billed_before_qty"], pl["unit"]) if before else "—"}'
                    f'<div class="sub">{inr(before, 0) if before else "nothing billed"}</div></td><td class="r">{this}</td></tr>')
    head = (f'<tr><th>Item</th><th class="r">Ordered on {h(po["po_number"])}</th>{"" if services else "<th class=r>Received</th>"}'
            f'<th class="r">Billed earlier</th><th class="r">This invoice</th></tr>')
    kind = "Services: no delivery receipt, so a 2-way match" if services else "Goods: a 3-way match"
    return (f'<div class="panel"><div class="panel-h"><span class="h3">Ordered, received, billed</span>'
            f'<span class="note">{kind}</span></div><div style="overflow-x:auto"><table class="tbl" style="border:0;border-radius:0">'
            f'{head}{"".join(rows)}</table></div></div>')


# ---------- the check log ----------

STAGE_NAMES = ["Receiving the file", "Reading the invoice", "Working out what it is", "GST validation",
               "Matching", "Fraud and duplicate controls", "The decision"]


def check_log(findings: list[dict]) -> str:
    out, last = [], None
    for f in findings:
        idx = rail_index(f["stage"])
        if idx != last:
            out.append(f'<li class="h"><span class="cap">{STAGE_NAMES[idx]}</span></li>')
            last = idx
        held = " held" if f.get("outcome") == 2 else ""
        icon = {"pass": "✓", "warn": "!", "fail": "✕"}[f["status"]]
        code = f'<span class="cd">{h(f["code"])}</span>' if f.get("code") and f["status"] != "pass" else ""
        detail = f'<div class="dd">{h(f["detail"])}</div>' if f.get("detail") and f["status"] != "pass" else ""
        out.append(f'<li class="{f["status"]}{held}"><span class="ic">{icon}</span><div><span class="tt">{h(f["title"])}</span>'
                   f'{code}{detail}</div></li>')
    return f'<ul class="log">{"".join(out)}</ul>'

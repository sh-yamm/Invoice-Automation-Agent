"""Documents for the trail viewer: the purchase order as it was sent to the vendor, and the goods receipt note.

They are built from the company records (in production they come from the ERP), printed as a one-page PDF and
rendered to a page image. Both are cached by their content, so a changed record gives a new document.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ap_agent.core.constants import BUYER_ADDRESS, BUYER_GSTIN, BUYER_NAME
from ap_agent.core.models import Grn, PurchaseOrder, Vendor
from ap_agent.core.money import fmt_inr
from ap_agent.reading.render import render_pages

INK = colors.HexColor("#2e1f17")
RUST = colors.HexColor("#b5502c")
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.8, leading=10)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=RUST)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=2)


def _amt(x) -> str:
    return fmt_inr(x).replace("₹", "")


def _qty(x: Decimal) -> str:
    return f"{x:,.0f}" if x == x.to_integral_value() else f"{x:,.2f}"


def _grid(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.4),
                           ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fdf1e7")),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ead9c6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ALIGN", (2, 1), (-1, -1), "RIGHT")]))
    return t


def _parties(left_title: str, vendor: Vendor):
    buyer = [Paragraph(f"<b>{left_title}</b>", SMALL), Paragraph(f"<b>{BUYER_NAME}</b>", BODY),
             Paragraph(BUYER_ADDRESS, SMALL), Paragraph(f"GSTIN: <b>{BUYER_GSTIN}</b>", SMALL)]
    seller = [Paragraph("<b>Vendor</b>", SMALL), Paragraph(f"<b>{vendor.name}</b>", BODY), Paragraph(vendor.address, SMALL),
              Paragraph(f"GSTIN: <b>{vendor.gstin}</b> · {vendor.email}", SMALL)]
    t = Table([[buyer, seller]], colWidths=[91 * mm, 91 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ead9c6")),
                           ("LINEAFTER", (0, 0), (0, 0), 0.5, colors.HexColor("#ead9c6"))]))
    return t


def _render(story, title: str, key: dict, out_dir: Path, stem: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:10]
    pdf = out_dir / f"{stem}-{digest}.pdf"
    png = pdf.with_suffix(".png")
    if png.exists():
        return png
    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=title, author=BUYER_NAME)
    doc.build(story)
    rendered = render_pages(pdf, out_dir / f"{stem}-{digest}-pages", dpi=150)[0]
    rendered.replace(png)
    return png


def po_document(po: PurchaseOrder, vendor: Vendor, out_dir: Path) -> Path:
    """The purchase order as sent to the vendor: buyer, vendor, lines, GST and totals."""
    rows = [["#", "Description", "HSN/SAC", "Qty", "Unit", "Rate", "GST %", "Amount"]]
    taxable, tax = Decimal("0"), Decimal("0")
    for l in po.lines:
        amount = l.qty * l.rate
        taxable += amount
        tax += amount * l.gst_rate / 100
        rows.append([str(l.line_no), Paragraph(l.description, BODY), l.hsn_sac, _qty(l.qty), l.unit, _amt(l.rate),
                     f"{l.gst_rate:g}", _amt(amount)])
    totals = Table([["Taxable value", _amt(taxable)], ["GST", _amt(tax)], ["Order total (Rs.)", _amt(taxable + tax)]],
                   colWidths=[46 * mm, 34 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8.6), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
                                ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, RUST)]))
    kind = {"goods": "Goods", "services": "Services", "blanket": "Blanket order"}.get(po.po_type, po.po_type)
    story = [Paragraph("PURCHASE ORDER", TITLE),
             Paragraph(f"<b>{po.po_number}</b> · {kind} · dated {po.po_date:%d %b %Y} · status {po.status}", BODY),
             Spacer(1, 8), _parties("Buyer", vendor), Spacer(1, 10),
             _grid(rows, [8 * mm, 62 * mm, 18 * mm, 16 * mm, 14 * mm, 22 * mm, 14 * mm, 28 * mm]), Spacer(1, 6), totals,
             Spacer(1, 12),
             Paragraph(f"Terms: payment {vendor.payment_terms_days} days from a valid tax invoice that quotes {po.po_number}. "
                       "Goods are accepted against a goods receipt note.", SMALL),
             Paragraph("Sent to the vendor by email.", SMALL)]
    key = {"po": po.model_dump(mode="json"), "vendor": vendor.model_dump(mode="json"), "buyer": BUYER_NAME}
    return _render(story, f"Purchase order {po.po_number}", key, out_dir, po.po_number)


def grn_document(grns: list[Grn], po: PurchaseOrder, vendor: Vendor, out_dir: Path) -> Path:
    """The goods receipt note: what the warehouse received and accepted against each PO line."""
    number, received = grns[0].grn_number, max(g.received_date for g in grns)
    rows = [["PO line", "Description", "Ordered", "Received", "Accepted", "Unit"]]
    for g in sorted(grns, key=lambda g: g.line_no):
        pl = po.line(g.line_no)
        rows.append([str(g.line_no), Paragraph(pl.description if pl else "", BODY), _qty(pl.qty) if pl else "",
                     _qty(g.received_qty), _qty(g.accepted_qty), pl.unit if pl else ""])
    story = [Paragraph("GOODS RECEIPT NOTE", TITLE),
             Paragraph(f"<b>{number}</b> · against <b>{po.po_number}</b> · received {received:%d %b %Y}", BODY),
             Spacer(1, 8), _parties("Received by", vendor), Spacer(1, 10),
             _grid(rows, [16 * mm, 76 * mm, 22 * mm, 22 * mm, 22 * mm, 24 * mm]), Spacer(1, 12),
             Paragraph("Recorded by the warehouse on delivery. The invoice is paid only for accepted quantities.", SMALL)]
    key = {"grns": [g.model_dump(mode="json") for g in grns], "po": po.po_number, "vendor": vendor.vendor_id}
    return _render(story, f"Goods receipt {number}", key, out_dir, number)

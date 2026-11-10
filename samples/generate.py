"""Build the demo invoice PDFs from samples/specs.py.

Three letterhead layouts (classic / modern / compact) so reading is not tied to one template,
a scanned variant (image-only, skewed, noisy, smudged date) and a hidden-text-layer variant.

Run from the repo root:  py -3.11 samples/generate.py
"""
from __future__ import annotations

import io
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from samples.specs import BUYER, SPECS, SampleSpec  # noqa: E402

from ap_agent.core.constants import STATE_CODES  # noqa: E402
from ap_agent.core.money import fmt_inr  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "pdf"
W, H = A4


def amt(x) -> str:
    return fmt_inr(x).replace("₹", "")


def qty(x) -> str:
    return f"{x:,.0f}" if x == x.to_integral_value() else f"{x:,.2f}"


# ---------- layout themes ----------

THEMES = {
    "classic": dict(font="Helvetica", bold="Helvetica-Bold", size=8.6, accent=colors.HexColor("#1F2A44"),
                    grid=True, head_bg=colors.HexColor("#E6E9EF"), zebra=False),
    "modern": dict(font="Helvetica", bold="Helvetica-Bold", size=8.8, accent=colors.HexColor("#0F6E6E"),
                   grid=False, head_bg=colors.HexColor("#0F6E6E"), zebra=False),
    "compact": dict(font="Helvetica", bold="Helvetica-Bold", size=7.8, accent=colors.HexColor("#7A2E1F"),
                    grid=False, head_bg=colors.HexColor("#F1E4DF"), zebra=True),
}


def _styles(t):
    base = ParagraphStyle("b", fontName=t["font"], fontSize=t["size"], leading=t["size"] * 1.3)
    return {
        "body": base,
        "small": ParagraphStyle("s", parent=base, fontSize=t["size"] - 1.2, leading=(t["size"] - 1.2) * 1.3,
                                textColor=colors.HexColor("#4A4F5C")),
        "name": ParagraphStyle("n", parent=base, fontName=t["bold"], fontSize=t["size"] + 6, leading=t["size"] + 9,
                               textColor=t["accent"]),
        "heading": ParagraphStyle("h", parent=base, fontName=t["bold"], fontSize=t["size"] + 4, alignment=TA_RIGHT,
                                  textColor=t["accent"]),
        "bold": ParagraphStyle("bb", parent=base, fontName=t["bold"]),
        "right": ParagraphStyle("r", parent=base, alignment=TA_RIGHT),
    }


def _qr(text: str, size: float = 26 * mm) -> Drawing:
    w = QrCodeWidget(text)
    b = w.getBounds()
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(w)
    return d


def _story(spec: SampleSpec):
    t, inv, sup = THEMES[spec.layout], spec.invoice, spec.supplier
    st = _styles(t)
    story = []

    supplier = [Paragraph(sup["name"], st["name"]), Paragraph(sup["address"], st["small"]),
                Paragraph(f"GSTIN: <b>{sup['gstin']}</b> &nbsp; State: {STATE_CODES[sup['state']]} ({sup['state']})",
                          st["small"]),
                Paragraph(f"Phone: {sup['phone']} &nbsp; Email: {sup['email']}", st["small"])]
    heading = [Paragraph(spec.doc_heading, st["heading"]), Paragraph("Original for recipient", st["small"])]
    if inv.irn:
        heading += [Paragraph(f"IRN: {inv.irn[:32]}<br/>{inv.irn[32:]}", st["small"]), _qr(inv.irn)]

    meta_rows = [("Invoice No.", inv.invoice_no), ("Invoice Date", inv.invoice_date.strftime("%d/%m/%Y"))]
    if inv.po_ref:
        meta_rows.append(("PO Ref.", inv.po_ref))
    meta_rows.append(("Place of Supply", f"{STATE_CODES[inv.place_of_supply_state]} ({inv.place_of_supply_state})"))
    if inv.period_start:
        meta_rows.append(("Billing Period", f"{inv.period_start:%d/%m/%Y} to {inv.period_end:%d/%m/%Y}"))
    if inv.consumer_no:
        meta_rows.append(("Account No.", inv.consumer_no))
    meta = Table([[Paragraph(k, st["small"]), Paragraph(f"<b>{v}</b>", st["body"])] for k, v in meta_rows],
                 colWidths=[28 * mm, 52 * mm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                              ("TOPPADDING", (0, 0), (-1, -1), 1.5)]))

    bill_to = [Paragraph("Bill to", st["small"]), Paragraph(f"<b>{BUYER['name']}</b>", st["body"]),
               Paragraph(BUYER["address"], st["small"])] + (
                  [Paragraph(f"GSTIN: <b>{inv.buyer_gstin}</b>", st["small"])] if inv.buyer_gstin else [])

    if spec.layout == "compact":
        top = Table([[supplier, [*heading, Spacer(1, 3), meta]]], colWidths=[100 * mm, 82 * mm])
        top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1, t["accent"])]))
        story += [top, Spacer(1, 6), Table([[bill_to]], colWidths=[182 * mm])]
    else:
        top = Table([[supplier, heading]], colWidths=[120 * mm, 62 * mm])
        style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.6, t["accent"])]
        if spec.layout == "classic":
            style.append(("BOX", (1, 0), (1, 0), 0.8, t["accent"]))
        top.setStyle(TableStyle(style))
        mid = Table([[bill_to, meta]], colWidths=[100 * mm, 82 * mm])
        mid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] +
                                ([("BOX", (0, 0), (-1, -1), 0.6, colors.grey), ("LINEAFTER", (0, 0), (0, 0), 0.6, colors.grey)]
                                 if spec.layout == "classic" else [])))
        story += [top, Spacer(1, 8), mid]
    story.append(Spacer(1, 8))

    head = ["#", "Description", "HSN/SAC", "Qty", "Unit", "Rate (Rs.)", "Taxable Value (Rs.)"]
    rows = [head] + [[str(i), Paragraph(l.description, st["body"]), l.hsn_sac or "", qty(l.qty), l.unit or "",
                      amt(l.rate), amt(l.taxable)] for i, l in enumerate(inv.lines, 1)]
    lines = Table(rows, colWidths=[8 * mm, 72 * mm, 18 * mm, 16 * mm, 14 * mm, 24 * mm, 30 * mm], repeatRows=1)
    ls = [("FONT", (0, 0), (-1, 0), t["bold"], t["size"]), ("FONT", (0, 1), (-1, -1), t["font"], t["size"]),
          ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("BACKGROUND", (0, 0), (-1, 0), t["head_bg"]),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if spec.layout == "modern" else colors.black)]
    if t["grid"]:
        ls.append(("GRID", (0, 0), (-1, -1), 0.5, colors.grey))
    else:
        ls.append(("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9CDD6")))
    if t["zebra"]:
        ls += [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FAF5F3")) for r in range(2, len(rows), 2)]
    lines.setStyle(TableStyle(ls))
    story += [lines, Spacer(1, 6)]

    tax_rows = [("Taxable Value", amt(inv.taxable_total))]
    rate = inv.lines[0].gst_rate
    if inv.cgst is not None:
        tax_rows += [(f"CGST @ {rate / 2:g}%", amt(inv.cgst)), (f"SGST @ {rate / 2:g}%", amt(inv.sgst))]
    if inv.igst is not None:
        tax_rows.append((f"IGST @ {rate:g}%", amt(inv.igst)))
    tax_rows += [("Round Off", amt(inv.round_off or 0)), ("Invoice Total (Rs.)", amt(inv.grand_total))]
    totals = Table([[Paragraph(k, st["bold"] if i == len(tax_rows) - 1 else st["body"]),
                     Paragraph(f"<b>{v}</b>" if i == len(tax_rows) - 1 else v, st["right"])]
                    for i, (k, v) in enumerate(tax_rows)], colWidths=[46 * mm, 34 * mm])
    totals.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 1, t["accent"]),
                                ("BOX", (0, 0), (-1, -1), 0.6, colors.grey) if t["grid"] else ("TOPPADDING", (0, 0), (0, 0), 1)]))
    words = Paragraph(f"<b>Amount in words:</b> {inv.amount_in_words}", st["body"])
    story += [Table([[words, totals]], colWidths=[102 * mm, 80 * mm],
                    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])), Spacer(1, 10)]

    bank = [Paragraph("<b>Bank details for payment</b>", st["body"]),
            Paragraph(f"{inv.bank_name} &nbsp; A/c No.: <b>{inv.bank_account}</b> &nbsp; IFSC: <b>{inv.ifsc}</b>", st["body"])]
    story += [Table([[bank]], colWidths=[182 * mm],
                    style=TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.grey)]))]
    for note in spec.notes:
        story += [Spacer(1, 4), Paragraph(f"<b>Note:</b> {note}", st["body"])]
    story += [Spacer(1, 18), Paragraph(f"For <b>{spec.supplier['name']}</b>", st["right"]), Spacer(1, 18),
              Paragraph("Authorised Signatory", st["right"]), Spacer(1, 10),
              Paragraph("Subject to local jurisdiction. This is a computer generated invoice.", st["small"])]
    if spec.injection:
        story += [Spacer(1, 6), Paragraph(spec.injection, ParagraphStyle(
            "inj", parent=st["small"], textColor=colors.HexColor("#9AA0AA"), fontSize=6.5))]
    return story


def _hidden_text(lines: list[str]):
    """Draw text that is invisible on the page but present in the PDF's text layer."""
    def on_page(canvas, doc):
        canvas.saveState()
        t = canvas.beginText(120 * mm, 95 * mm)
        t.setTextRenderMode(3)
        t.setFont("Helvetica", 9)
        for line in lines:
            t.textLine(line)
        canvas.drawText(t)
        canvas.restoreState()
    return on_page


def _build(spec: SampleSpec, path: Path) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"{spec.doc_heading.title()} {spec.invoice.invoice_no}", author=spec.supplier["name"])
    on_page = _hidden_text(spec.hidden_text) if spec.hidden_text else (lambda c, d: None)
    doc.build(_story(spec), onFirstPage=on_page, onLaterPages=on_page)


def _scan(clean_pdf: Path, out: Path, spec: SampleSpec, dpi: int = 150) -> None:
    """Turn a clean PDF into an image-only 'scan': grey, skewed, noisy, with the date smudged."""
    import pdfplumber
    import pypdfium2 as pdfium

    scale = dpi / 72
    page = pdfium.PdfDocument(str(clean_pdf))[0]
    img = page.render(scale=scale).to_pil().convert("L")
    date_text = spec.invoice.invoice_date.strftime("%d/%m/%Y")
    with pdfplumber.open(clean_pdf) as pdf:
        words = [w for w in pdf.pages[0].extract_words() if w["text"] == date_text]
    draw = ImageDraw.Draw(img)
    for w in words:
        box = tuple(int(v * scale) for v in (w["x0"] - 2, w["top"] - 2, w["x1"] + 2, w["bottom"] + 2))
        region = img.crop(box).filter(ImageFilter.GaussianBlur(1.3))
        img.paste(region, box)
        draw.arc((box[0] + 10, box[1] - 3, box[2] + 4, box[3] + 6), 200, 340, fill=165, width=2)
    rng = random.Random(8)
    noise = Image.effect_noise(img.size, 28).point(lambda v: 255 if v > 128 else v)
    img = Image.blend(img, noise, 0.10)
    for _ in range(900):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        draw = ImageDraw.Draw(img)
        draw.point((x, y), fill=rng.randrange(90, 170))
    img = img.rotate(1.2, resample=Image.BICUBIC, expand=False, fillcolor=245)
    img = ImageOps.autocontrast(img.filter(ImageFilter.GaussianBlur(0.6)), cutoff=1)
    img.convert("RGB").save(out, "PDF", resolution=dpi)


def generate(spec: SampleSpec, out_dir: Path = OUT_DIR) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec.id}.pdf"
    if spec.scanned:
        clean = out_dir / f"{spec.id}.clean.tmp.pdf"
        _build(spec, clean)
        _scan(clean, path, spec)
        clean.unlink()
    else:
        _build(spec, path)
    return path


if __name__ == "__main__":
    for s in SPECS.values():
        print("wrote", generate(s))

"""Render PDF pages to images for the page parser and the UI."""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from ap_agent.reading._pdfium import PDFIUM_LOCK


def render_pages(pdf: Path, out_dir: Path, dpi: int = 200) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(str(pdf))
        try:
            for i in range(len(doc)):
                page = doc[i]
                image = page.render(scale=dpi / 72).to_pil().convert("RGB")
                page.close()
                p = out_dir / f"page-{i + 1}.png"
                image.save(p)
                paths.append(p)
        finally:
            doc.close()
    return paths

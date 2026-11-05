"""Render PDF pages to images for the page parser and the UI."""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium


def render_pages(pdf: Path, out_dir: Path, dpi: int = 200) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(pdf))
    paths = []
    for i in range(len(doc)):
        p = out_dir / f"page-{i + 1}.png"
        doc[i].render(scale=dpi / 72).to_pil().convert("RGB").save(p)
        paths.append(p)
    return paths

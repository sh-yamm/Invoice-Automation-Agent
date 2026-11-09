"""Inspect an uploaded file: is it a readable PDF, how many pages, who produced it, when."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pypdfium2 as pdfium

from ap_agent.reading._pdfium import PDFIUM_LOCK


def _pdf_date(v: str | None) -> str | None:
    """'D:20261029120000+05'00'' → '2026-10-29'."""
    if not v:
        return None
    s = v[2:] if v.startswith("D:") else v
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8])).isoformat()
    except (ValueError, IndexError):
        return None


def inspect_pdf(path: Path) -> dict:
    data = Path(path).read_bytes()
    info = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "pages": 0, "encrypted": False,
            "error": None, "producer": None, "creator": None, "created": None, "modified": None}
    if not data.startswith(b"%PDF-"):
        info["error"] = "the file is not a PDF"
        return info
    with PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as e:
            if "password" in str(e).lower():
                info["encrypted"] = True
            else:
                info["error"] = f"the PDF could not be opened ({e})"
            return info
        try:
            info["pages"] = len(doc)
            meta = doc.get_metadata_dict()
        finally:
            doc.close()
    info.update(producer=meta.get("Producer") or None, creator=meta.get("Creator") or None,
                created=_pdf_date(meta.get("CreationDate")), modified=_pdf_date(meta.get("ModDate")))
    if info["pages"] == 0:
        info["error"] = "the PDF has no pages"
    return info

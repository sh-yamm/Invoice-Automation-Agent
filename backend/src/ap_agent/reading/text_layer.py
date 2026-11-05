"""The text embedded in a digital PDF, one block per line, with positions normalised to 0–1."""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from ap_agent.core.models import ParseBlock


def text_layer(pdf: Path) -> list[ParseBlock]:
    blocks: list[ParseBlock] = []
    with pdfplumber.open(str(pdf)) as doc:
        for n, page in enumerate(doc.pages, start=1):
            words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
            lines: dict[int, list[dict]] = {}
            for w in words:
                lines.setdefault(round(w["top"] / 3), []).append(w)
            for ws in lines.values():
                ws.sort(key=lambda w: w["x0"])
                x0, x1 = min(w["x0"] for w in ws), max(w["x1"] for w in ws)
                top, bottom = min(w["top"] for w in ws), max(w["bottom"] for w in ws)
                blocks.append(ParseBlock(page=n, text=" ".join(w["text"] for w in ws), cls="TextLayer",
                                         box=(x0 / page.width, top / page.height, x1 / page.width, bottom / page.height)))
    return blocks

"""Read the page parser's output into text blocks with boxes.

The parser returns segments like  <x_0.07><y_0.13>Invoice No. **SGOF/26-27/0412**<x_0.80><y_0.14><class_Text>
with tables as LaTeX `tabular`. We keep the text readable and the box normalised to 0–1.
"""
from __future__ import annotations

import re

from ap_agent.core.models import ParseBlock

_TAG = re.compile(r"<x_([\d.]+)><y_([\d.]+)>(?:<class_([^>]+)>)?")


def clean_text(t: str) -> str:
    t = re.sub(r"\\begin\{tabular\}\{[^}]*\}|\\end\{tabular\}", "", t)
    t = re.sub(r"\\thead\{(.*?)\}", r"\1", t)
    t = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{(.*?)\}", r"\1", t)
    t = t.replace("\\\\", "\n").replace(" & ", " | ").replace("\\%", "%").replace("\\#", "#").replace("\\&", "&")
    t = t.replace("**", "")
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = re.sub(r"[ \t]+", " ", t)
    return "\n".join(line.strip() for line in t.splitlines() if line.strip())


def parse_blocks(content: str, page: int) -> list[ParseBlock]:
    tags = list(_TAG.finditer(content or ""))
    blocks: list[ParseBlock] = []
    i = 0
    while i < len(tags):
        start = tags[i]
        if start.group(3):           # a stray end tag with no start; skip it
            i += 1
            continue
        nxt = tags[i + 1] if i + 1 < len(tags) else None
        end_pos = nxt.start() if nxt else len(content)
        text = clean_text(content[start.end():end_pos])
        x0, y0 = float(start.group(1)), float(start.group(2))
        if nxt and nxt.group(3):     # proper end tag: <x><y><class_K>
            box, cls, i = (x0, y0, float(nxt.group(1)), float(nxt.group(2))), nxt.group(3), i + 2
        else:                        # missing end tag: keep the block with a nominal box
            box, cls, i = (x0, y0, min(1.0, x0 + 0.3), min(1.0, y0 + 0.02)), "Text", i + 1
        if text:
            blocks.append(ParseBlock(page=page, text=text, box=box, cls=cls))
    return blocks

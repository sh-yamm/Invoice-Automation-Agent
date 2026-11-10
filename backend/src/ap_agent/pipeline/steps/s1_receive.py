"""Stage 1 · Receive: fingerprint the file, render page images, read the page with OCR.

ingest → render → parse
"""
from __future__ import annotations

from ap_agent.pipeline.steps._shared import *  # noqa: F401,F403  (helpers, models, checks)


@node("ingest", "ingest")
def ingest(state, deps):
    from ap_agent.reading.pdfinfo import inspect_pdf
    aop = load_aop(deps.aop_path)
    info = inspect_pdf(state["pdf_path"])
    other_id = deps.store.case_by_sha(info["sha256"], exclude_case=state["case_id"])
    same = None
    if other_id:
        other = deps.store.get_case(other_id)
        same = {"case_id": other_id, "invoice_no": other.get("invoice_no"),
                "outcome": (other["outcome"].name.replace("_", " ").lower() if other.get("outcome") is not None
                            else "in progress")}
    st = {**state, "pdf_info": info, "same_file_case": same}
    found = run_checks("ingest", make_ctx(st, deps, aop))
    return {"pdf_info": info, "same_file_case": same, "findings": _record(deps, state, found),
            "stopped": any(f.stop for f in found), "aop_version": aop.version, "restart": False}


@node("render", "ingest")
def render(state, deps):
    out = deps.files_dir / state["case_id"] / "pages"
    pages = render_pages(state["pdf_path"], out)
    layer = text_layer(state["pdf_path"])
    kind = "digital PDF with a text layer" if layer else "scanned copy, no text layer"
    f = _ok(f"Rendered {len(pages)} page(s): {kind}", "render", "ingest")
    return {"pages": [str(p) for p in pages], "text_blocks": [b.model_dump() for b in layer],
            "findings": _record(deps, state, [f])}


@node("parse", "ingest")
def parse(state, deps):
    blocks = []
    try:
        for n, png in enumerate(state["pages"], start=1):
            content = deps.gateway.parse_page(png, case_id=state["case_id"], cache_key=_cache(state, f"parse/p{n}"))
            blocks += parse_blocks(content, page=n)
    except AiUnavailable:
        if not state.get("text_blocks"):
            raise  # a scan has nothing else to check a reading against: hold (fail closed)
        # A digital PDF carries its own text with positions: read from that instead of the page image.
        blocks = [ParseBlock(**b) for b in state["text_blocks"]]
        f = Finding(check="parse_pages", stage="ingest", status=Status.WARN,
                    title="Page parser unavailable: read the PDF's own text instead",
                    detail="The OCR service could not be reached, so fields were read from the text embedded in the "
                           "PDF. The check that compares that text with the visible page could not run.")
        return {"parse_blocks": [b.model_dump() for b in blocks], "findings": _record(deps, state, [f])}
    f = _ok(f"Parsed {len(blocks)} text blocks with positions", "parse_pages", "ingest",
            "nemotron-3.5-parse read each page image")
    return {"parse_blocks": [b.model_dump() for b in blocks], "findings": _record(deps, state, [f])}

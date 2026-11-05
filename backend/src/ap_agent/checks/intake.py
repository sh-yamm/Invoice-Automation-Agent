"""Stage 1 checks, in three places in the graph:

- ingest:    is this a readable PDF we haven't seen before?
- reconcile: does the hidden text match the page, are there edit marks, is there text aimed at the AI?
- read:      was every key field read with enough confidence?
"""
from __future__ import annotations

import re
from datetime import date

from ap_agent.checks.framework import CheckContext, check

ALL = {"all"}
EDITORS = ("ilovepdf", "smallpdf", "sejda", "pdf-xchange", "phantompdf", "pdfescape", "nitro", "pdffiller",
           "pdf candy", "foxit pdf editor", "adobe acrobat pro")
INJECTION = [
    r"ignore (?:all |any )?(?:previous|prior|above) instructions",
    r"ignore all instructions",
    r"pre-?approved",
    r"(?:note|message|instruction)s? (?:to|for) (?:the )?(?:ai|assistant|model|system|agent)",
    r"skip (?:all |the )?(?:checks|validation|verification)",
    r"system prompt",
    r"you are (?:an? )?(?:ai|assistant|language model)",
    r"approve (?:this|immediately|without)",
]
_AMOUNT = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d{2})?|\b\d+\.\d{2}\b")
_ACCOUNT = re.compile(r"\b\d{9,18}\b")
_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
KEY_FIELDS = {"invoice_no": "invoice number", "invoice_date": "invoice date", "supplier_gstin": "supplier GSTIN",
              "buyer_gstin": "buyer GSTIN", "taxable_total": "taxable value", "grand_total": "invoice total",
              "po_ref": "PO number", "bank_account": "bank account", "period_start": "billing period"}


def _tokens(texts: list[str]) -> dict[str, set[str]]:
    joined = "\n".join(texts)
    return {"amount": {a.replace(",", "") for a in _AMOUNT.findall(joined)},
            "account": set(_ACCOUNT.findall(joined)), "gstin": set(_GSTIN.findall(joined))}


# ---------- ingest ----------

@check("file_fingerprint", "ingest", ALL, "This exact file has not been processed before")
def file_fingerprint(ctx: CheckContext):
    other = ctx.scratch.get("same_file_case")
    if other:
        return [ctx.fail("DUPLICATE_EXACT", "This exact file was already processed", stop=True,
                         data={"other_case": other["case_id"], "other_no": other.get("invoice_no") or "the same file",
                               "other_outcome": other.get("outcome") or "in progress"})]
    return []


@check("readable", "ingest", ALL, "File is a readable PDF")
def readable(ctx: CheckContext):
    info = ctx.scratch.get("pdf_info") or {}
    if info.get("error"):
        return [ctx.fail("UNREADABLE_DOCUMENT", "The file could not be read", stop=True,
                         data={"reason": info["error"]})]
    return [ctx.ok(f"Readable PDF, {info.get('pages', 0)} page(s)")]


@check("encrypted", "ingest", ALL, "File is not password protected")
def encrypted(ctx: CheckContext):
    if (ctx.scratch.get("pdf_info") or {}).get("encrypted"):
        return [ctx.fail("ENCRYPTED_DOCUMENT", "The PDF is password protected", stop=True)]
    return []


# ---------- reconcile ----------

@check("text_layer_match", "reconcile", ALL, "Embedded text matches what the page shows")
def text_layer_match(ctx: CheckContext):
    layer = ctx.scratch.get("text_blocks") or []
    if not layer:
        return [ctx.ok("No embedded text (scanned copy); nothing to compare")]
    seen = _tokens([b.text for b in ctx.scratch.get("parse_blocks") or []])
    hidden = _tokens([b.text for b in layer])
    extra = {k: sorted(hidden[k] - seen[k]) for k in hidden if hidden[k] - seen[k]}
    if extra:
        figures = [_indian(a) for a in extra.get("amount", [])] + extra.get("account", []) + extra.get("gstin", [])
        return [ctx.fail("TEXT_LAYER_MISMATCH", "Hidden text differs from the visible page", data={
            "hidden": ", ".join(figures), "visible": "different figures", "tokens": extra})]
    return []


def _indian(a: str) -> str:
    whole, _, frac = a.partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail]) + (f".{frac}" if frac else "")


@check("tamper_signals", "reconcile", ALL, "No signs of editing after the PDF was created")
def tamper_signals(ctx: CheckContext):
    info = ctx.scratch.get("pdf_info") or {}
    signals = []
    producer = " ".join(filter(None, [info.get("producer"), info.get("creator")])).lower()
    if any(e in producer for e in EDITORS):
        signals.append(f"saved by an editing tool ({info.get('producer') or info.get('creator')})")
    if info.get("created") and info.get("modified"):
        gap = (date.fromisoformat(info["modified"]) - date.fromisoformat(info["created"])).days
        if gap > 1:
            signals.append(f"modified {gap} days after it was created")
    if signals:
        return [ctx.warn("DOCUMENT_TAMPER_SIGNALS", "Signs the PDF was edited", data={"signals": "; ".join(signals)})]
    return []


@check("injection_scan", "reconcile", ALL, "No instructions aimed at the AI")
def injection_scan(ctx: CheckContext):
    texts = [b.text for b in (ctx.scratch.get("parse_blocks") or [])] + [b.text for b in (ctx.scratch.get("text_blocks") or [])]
    joined = "\n".join(texts)
    for pattern in INJECTION:
        m = re.search(pattern, joined, re.I)
        if m:
            line = next((l for l in joined.splitlines() if m.group(0).lower() in l.lower()), m.group(0)).strip()
            return [ctx.fail("SUSPICIOUS_INSTRUCTIONS_IN_DOCUMENT", "Text in the invoice is addressed to the AI",
                             data={"snippet": line[:160]})]
    return []


# ---------- read ----------

@check("field_confidence", "read", ALL, "Key fields read with enough confidence")
def field_confidence(ctx: CheckContext):
    inv, minimum = ctx.invoice, ctx.aop.confidence.min_field
    low = [(f, label, inv.confidence.get(f, 1.0)) for f, label in KEY_FIELDS.items()
           if getattr(inv, f) is not None and inv.confidence.get(f, 1.0) < minimum]
    if low:
        return [ctx.fail("LOW_CONFIDENCE_FIELD", f"Unsure about {', '.join(l for _, l, _ in low)}",
                         evidence=[e for f, _, _ in low for e in ctx.ev(f)],
                         data={"fields": ", ".join(f"the {l}" for _, l, _ in low),
                               "confidence": ", ".join(f"{c:.0%}" for _, _, c in low),
                               "values": {f: str(getattr(inv, f)) for f, _, _ in low}})]
    return []

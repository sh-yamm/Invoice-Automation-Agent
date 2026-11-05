"""RealAi: the model-backed implementation of checks.framework.AiHelpers."""
from __future__ import annotations

import math
from decimal import Decimal

from rapidfuzz import fuzz

from ap_agent.ai.gateway import AiUnavailable
from ap_agent.core.models import Invoice, PurchaseOrder

GL_SCHEMA = {"type": "object", "required": ["options"], "properties": {"options": {"type": "array", "items": {
    "type": "object", "required": ["gl_code", "confidence"],
    "properties": {"gl_code": {"type": "string"}, "cost_centre": {"type": ["string", "null"]},
                   "confidence": {"type": "number"}, "why": {"type": ["string", "null"]}}}}}}
PAIR_SCHEMA = {"type": "object", "required": ["line_no", "confidence"],
               "properties": {"line_no": {"type": ["integer", "null"]}, "confidence": {"type": "number"},
                              "why": {"type": ["string", "null"]}}}


class RealAi:
    def __init__(self, gateway, repo, store, case_id: str | None, cache_prefix: str | None = None):
        self.gw, self.repo, self.store, self.case_id, self.prefix = gateway, repo, store, case_id, cache_prefix
        self._vec: dict[str, list[float]] = {}

    def _key(self, name: str) -> str | None:
        return f"{self.prefix}/{name}" if self.prefix else None

    # ---------- similarity (embeddings) ----------
    def _vectors(self, texts: list[str]) -> None:
        missing = [t for t in dict.fromkeys(texts) if t not in self._vec]
        if missing:
            for t, v in zip(missing, self.gw.embed(missing)):
                self._vec[t] = v

    def similarity(self, a: str, b: str) -> float:
        a, b = (a or "").strip(), (b or "").strip()
        if not a or not b:
            return 0.0
        if a.lower() == b.lower():
            return 1.0
        try:
            self._vectors([a, b])
        except AiUnavailable:  # a lookup aid, not a decision: fall back to string similarity
            return fuzz.token_set_ratio(a, b) / 100
        x, y = self._vec[a], self._vec[b]
        nx, ny = math.sqrt(sum(i * i for i in x)), math.sqrt(sum(j * j for j in y))
        return max(0.0, min(1.0, sum(i * j for i, j in zip(x, y)) / (nx * ny))) if nx and ny else 0.0

    # ---------- PO inference ----------
    def rank_po_candidates(self, invoice: Invoice, pos: list[PurchaseOrder]) -> list[tuple[str, float, str]]:
        """Score each open PO by how well its lines match the invoice lines (embeddings + same rate + fits balance)."""
        if not invoice.lines or not pos:
            return []
        ranked = []
        for po in pos:
            sims, rate_hits, best_desc = [], 0, []
            for line in invoice.lines:
                score, pl = max(((self.similarity(line.description, pl.description), pl) for pl in po.lines),
                                key=lambda s: s[0])
                sims.append(score)
                best_desc.append(pl.description)
                rate_hits += int(pl.rate == line.rate)
            score = sum(sims) / len(sims) * (1.0 if rate_hits else 0.9)
            invoiced = self.store.ledger.invoiced(po.po_number)[1] if self.store else Decimal("0")
            this = invoice.taxable_total or sum((l.taxable for l in invoice.lines), Decimal("0"))
            if invoiced + this > po.value:
                score *= 0.8
            why = f"items match {', '.join(dict.fromkeys(best_desc))}" + ("; same rate" if rate_hits else "")
            ranked.append((po.po_number, round(score, 2), why))
        return sorted(ranked, key=lambda r: -r[1])

    # ---------- line pairing tie-break ----------
    def pair_tiebreak(self, inv_line, candidates) -> tuple[int | None, float, str]:
        listing = "\n".join(f"- line {pl.line_no}: {pl.description} ({pl.qty} {pl.unit} @ {pl.rate})" for pl in candidates)
        msgs = [{"role": "system", "content": "You match an invoice line to the purchase-order line for the same item. "
                                              "Reply with JSON only: {\"line_no\": <number or null>, \"confidence\": 0-1, "
                                              "\"why\": \"...\"}. Use null if none is the same item."},
                {"role": "user", "content": f"Invoice line: {inv_line.description} ({inv_line.qty} {inv_line.unit} @ "
                                            f"{inv_line.rate})\nPO lines:\n{listing}"}]
        data, _ = self.gw.chat_json("fast", msgs, PAIR_SCHEMA, case_id=self.case_id, node="pair_lines",
                                    cache_key=self._key(f"pair/{inv_line.description[:40]}"))
        valid = {pl.line_no for pl in candidates}
        line_no = data.get("line_no") if data.get("line_no") in valid else None
        return line_no, float(data.get("confidence", 0) or 0), data.get("why") or ""

    # ---------- GL coding ----------
    def gl_code(self, invoice: Invoice, accounts) -> list[tuple[str, str, float, str]]:
        acct = {a.gl_code: a for a in accounts}
        listing = "\n".join(f"- {a.gl_code} {a.name}: {a.description} (category {a.category}, default cost centre "
                            f"{a.cost_centre_default})" for a in accounts)
        lines = "; ".join(l.description for l in invoice.lines)
        msgs = [{"role": "system", "content": "You code PO-less vendor invoices to the general ledger for an Indian "
                                              "company. Choose up to 3 accounts from the chart of accounts, best first. "
                                              "Reply with JSON only: {\"options\": [{\"gl_code\": ..., \"cost_centre\": "
                                              "..., \"confidence\": 0-1, \"why\": ...}]}"},
                {"role": "user", "content": f"Vendor: {invoice.supplier_name}\nLines: {lines}\n"
                                            f"Chart of accounts:\n{listing}"}]
        data, _ = self.gw.chat_json("agent", msgs, GL_SCHEMA, case_id=self.case_id, node="gl_coding",
                                    cache_key=self._key("gl_code"))
        out = []
        for o in data.get("options", []):
            code = str(o.get("gl_code", "")).strip()
            if code in acct:
                out.append((code, o.get("cost_centre") or acct[code].cost_centre_default,
                            float(o.get("confidence", 0) or 0), o.get("why") or ""))
        return sorted(out, key=lambda r: -r[2])

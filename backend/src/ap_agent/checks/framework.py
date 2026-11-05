"""The check framework: one registry, one context, one Finding shape.

A check is a plain function `fn(ctx) -> list[Finding]`. It returns only what went wrong (or a warning);
if it returns nothing, the framework records a pass finding with the check's title, so every check
always leaves a trace in the case record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Protocol

from ap_agent.core.models import Evidence, Finding, Invoice, PurchaseOrder, Status, Vendor
from ap_agent.rulebook.loader import Aop, render_reason


class AiHelpers(Protocol):
    """The few judgment calls a check may delegate to a model. Everything else is code."""

    def rank_po_candidates(self, invoice: Invoice, pos: list[PurchaseOrder]) -> list[tuple[str, float, str]]: ...

    def pair_tiebreak(self, inv_line, candidates) -> tuple[int | None, float, str]: ...

    def gl_code(self, invoice: Invoice, accounts) -> list[tuple[str, str, float, str]]: ...

    def similarity(self, a: str, b: str) -> float: ...


@dataclass
class LinePair:
    inv_index: int
    po_line_no: int | None
    method: str  # hsn | similarity | agent | header
    confidence: float


@dataclass
class CheckContext:
    case_id: str
    invoice: Invoice
    repo: object
    ledger: object
    history: object
    aop: Aop
    ai: AiHelpers
    doc_type: str | None = None
    txn_type: str | None = None
    vendor: Vendor | None = None
    po: PurchaseOrder | None = None
    pairs: list[LinePair] = field(default_factory=list)
    scratch: dict = field(default_factory=dict)
    today: date = field(default_factory=date.today)
    _check: str = ""
    _stage: str = ""

    def _finding(self, status, code, title, detail, evidence, data, stop) -> Finding:
        outcome = self.aop.reasons[code].outcome if code else None
        if code and not detail:
            detail = render_reason(self.aop, code, **(data or {}))[0]
        return Finding(check=self._check, stage=self._stage, status=status, code=code, outcome=outcome,
                       title=title, detail=detail, evidence=list(evidence or []), data=dict(data or {}), stop=stop)

    def ok(self, title: str, detail: str = "", evidence: list[Evidence] | None = None, data: dict | None = None) -> Finding:
        return self._finding(Status.PASS, None, title, detail, evidence, data, False)

    def fail(self, code: str, title: str, detail: str = "", evidence: list[Evidence] | None = None,
             data: dict | None = None, stop: bool = False) -> Finding:
        status = Status.WARN if self.aop.reasons[code].outcome is None else Status.FAIL
        return self._finding(status, code, title, detail, evidence, data, stop)

    def warn(self, code: str, title: str, detail: str = "", evidence: list[Evidence] | None = None,
             data: dict | None = None) -> Finding:
        return self._finding(Status.WARN, code, title, detail, evidence, data, False)

    def ev(self, field_name: str) -> list[Evidence]:
        """Evidence pointing at where a field was read on the page (if known)."""
        src = self.invoice.sources.get(field_name)
        return [src] if src else [Evidence(field=field_name)]


@dataclass
class CheckSpec:
    id: str
    stage: str
    paths: set[str]
    title: str
    fn: Callable[[CheckContext], list[Finding] | Finding | None]


REGISTRY: dict[str, CheckSpec] = {}


def check(id: str, stage: str, paths: set[str], title: str):
    def register(fn):
        REGISTRY[id] = CheckSpec(id, stage, set(paths), title, fn)
        return fn
    return register


def _applies(spec: CheckSpec, path: str | None) -> bool:
    return "all" in spec.paths or (path is not None and path in spec.paths)


def required_checks(path: str) -> list[str]:
    _load_all()
    return [s.id for s in REGISTRY.values() if _applies(s, path)]


def run_checks(stage: str, ctx: CheckContext, path: str | None = None) -> list[Finding]:
    """Run every registered check for a stage (and path). Exceptions become TOOL_ERROR holds."""
    _load_all()
    path = path or ctx.txn_type
    out: list[Finding] = []
    for spec in [s for s in REGISTRY.values() if s.stage == stage and _applies(s, path)]:
        ctx._check, ctx._stage = spec.id, stage
        try:
            result = spec.fn(ctx)
            found = [result] if isinstance(result, Finding) else list(result or [])
        except Exception as e:  # fail closed: a broken check never lets an invoice through
            found = [ctx.fail("TOOL_ERROR", f"Check failed to run: {spec.title}",
                              data={"check": spec.id, "error": f"{type(e).__name__}: {e}"})]
        if not found:
            found = [ctx.ok(spec.title)]
        out.extend(found)
    return out


_LOADED = False


def _load_all() -> None:
    """Import the stage modules so their checks register."""
    global _LOADED
    if not _LOADED:
        _LOADED = True
        import ap_agent.checks  # noqa: F401  (the package __init__ imports every stage module)

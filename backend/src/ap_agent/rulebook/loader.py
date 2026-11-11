"""Load, save and version the rulebook (rulebook/aop.yaml).

Saving edits values in place so the plain-English comments next to each value survive.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel

from ap_agent.core.models import Outcome

_OUTCOMES = {
    "approved": Outcome.APPROVED,
    "signoff": Outcome.NEEDS_SIGNOFF,
    "hold": Outcome.ON_HOLD,
    "reject": Outcome.REJECTED,
    "warn": None,
}
_OUTCOME_NAMES = {v: k for k, v in _OUTCOMES.items()}


class LockedRuleError(ValueError):
    """Raised when a save would change a locked rule."""


class PriceTolerance(BaseModel):
    over_pct: Decimal
    over_abs_inr: Decimal


class Tolerance(BaseModel):
    price: PriceTolerance
    qty_over_ordered_pct: Decimal
    qty_over_received_pct: Decimal
    po_balance_over_pct: Decimal
    contract_amount_pct: Decimal


class Authority(BaseModel):
    auto_approve_limit_inr: Decimal
    po_less_auto_limit_inr: Decimal
    split_window_days: int


class Duplicates(BaseModel):
    window_days: int
    min_similarity_pct: int


class Confidence(BaseModel):
    min_field: float
    po_inference_min: float
    classification_min: float
    gl_coding_min: float


class Reason(BaseModel):
    code: str
    title: str = ""  # the reason's plain name, shown in the app instead of the code
    outcome: Outcome | None
    owner: str
    explain: str
    next: str
    priority: int


class Aop(BaseModel):
    version: int
    region: str
    last_edit: dict
    owns: str
    sources_of_truth: dict[str, str]
    authority: Authority
    tolerance: Tolerance
    duplicates: Duplicates
    confidence: Confidence
    po_less_allowed_categories: list[str]
    locked: set[str]
    reasons: dict[str, Reason]


# Sections a person may tune from the UI; everything else is edited in the file.
_TUNABLE = ("authority", "tolerance", "duplicates", "confidence", "po_less_allowed_categories")


def load_aop(path: Path) -> Aop:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    reasons = {}
    for i, r in enumerate(raw.pop("reasons")):
        reasons[r["code"]] = Reason(
            code=r["code"], title=r.get("title", ""), outcome=_OUTCOMES[r["outcome"]], owner=r["owner"],
            explain=r["explain"], next=r["next"], priority=i,
        )
    return Aop(**raw, reasons=reasons)


class _Blank(dict):
    def __missing__(self, key):
        return "—"


def render_reason(aop: Aop, code: str, **values) -> tuple[str, str]:
    """Fill a reason's templates. Missing values render as a dash instead of failing."""
    r = aop.reasons[code]
    vals = _Blank({k: v for k, v in values.items() if v is not None})
    return r.explain.format_map(vals), r.next.format_map(vals)


def _check_locks(current: Aop, new: Aop) -> None:
    if new.locked != current.locked:
        raise LockedRuleError("The list of locked rules cannot be changed from the rulebook editor.")
    for code in current.locked:
        if new.reasons[code].outcome != current.reasons[code].outcome:
            raise LockedRuleError(f"{code} is locked; its outcome cannot be changed.")


def _flatten(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _yaml_scalar(v) -> str:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (list, dict)):
        return yaml.safe_dump(v, default_flow_style=True, sort_keys=False).strip()
    return yaml.safe_dump(v).strip().removesuffix("...").strip()


_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_]*):(?P<sep> *)(?P<value>[^#\n]*?)(?P<comment> +#.*)?$")


def _set_scalars(text: str, changes: dict[str, object]) -> str:
    """Replace values at dotted paths, keeping indentation and trailing comments."""
    stack: list[tuple[int, str]] = []
    out = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m and not line.lstrip().startswith("-"):
            indent = len(m["indent"])
            while stack and stack[-1][0] >= indent:
                stack.pop()
            path = ".".join([k for _, k in stack] + [m["key"]])
            if m["value"].strip() == "":
                stack.append((indent, m["key"]))
            elif path in changes:
                comment = m["comment"] or ""
                line = f'{m["indent"]}{m["key"]}: {_yaml_scalar(changes[path])}{comment}'
        out.append(line)
    return "\n".join(out) + "\n"


def save_aop(aop: Aop, path: Path, editor: str, why: str) -> Aop:
    """Save tunable values, archive the previous version, bump the version."""
    path = Path(path)
    current = load_aop(path)
    _check_locks(current, aop)

    old = _flatten({k: getattr(current, k) if not isinstance(getattr(current, k), BaseModel)
                    else getattr(current, k).model_dump() for k in _TUNABLE})
    new = _flatten({k: getattr(aop, k) if not isinstance(getattr(aop, k), BaseModel)
                    else getattr(aop, k).model_dump() for k in _TUNABLE})
    changes = {k: v for k, v in new.items() if old.get(k) != v}
    changes["version"] = current.version + 1
    changes["last_edit"] = {"editor": editor, "why": why, "at": datetime.now().isoformat(timespec="seconds")}

    text = path.read_text(encoding="utf-8")
    versions = path.parent / "versions"
    versions.mkdir(exist_ok=True)
    (versions / f"v{current.version}.yaml").write_text(text, encoding="utf-8")
    path.write_text(_set_scalars(text, changes), encoding="utf-8")
    return load_aop(path)


def outcome_name(outcome: Outcome | None) -> str:
    return _OUTCOME_NAMES[outcome]

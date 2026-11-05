"""Normalisation: turn values as printed into values the checks can compare."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# ---------- money ----------

_CURRENCY = re.compile(r"(?i)\b(rs|inr|rupees?)\b\.?|₹|/-")
_SCALE = re.compile(r"(?i)\s*(l|lakh|lakhs|lac|lacs|cr|crore|crores)\s*$")
_SCALES = {"l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
           "cr": 10_000_000, "crore": 10_000_000, "crores": 10_000_000}


def parse_inr(x) -> Decimal | None:
    """'1,29,000.00', 'Rs. 58,275/-', '₹ 2.84 L', '(1,000)' → Decimal. Anything else → None."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, (int, float)):
        return Decimal(str(x))
    s = _CURRENCY.sub("", str(x)).strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    scale = 1
    m = _SCALE.search(s)
    if m:
        scale = _SCALES[m.group(1).lower()]
        s = s[: m.start()]
    s = s.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        value = Decimal(s) * scale
    except InvalidOperation:
        return None
    if scale != 1:
        value = value.quantize(Decimal("1"))
    return -value if negative else value


def to_exclusive(amount: Decimal, gst_rate: Decimal) -> Decimal:
    """Remove GST from a tax-inclusive amount."""
    return (Decimal(amount) / (1 + Decimal(gst_rate) / 100)).quantize(Decimal("0.01"))


# ---------- invoice numbers ----------

def normal_invoice_no(s: str | None) -> str:
    """A comparable form of an invoice number.

    INV-001 = INV001 = 1, and SKL/1043-A = SKL-1043 (a trailing single-letter revision is dropped).
    """
    if not s:
        return ""
    parts = [p for p in re.split(r"[\s/\-_.]+", s.strip().upper()) if p]
    if len(parts) > 1 and re.fullmatch(r"[A-Z]", parts[-1]) and parts[-2][-1:].isdigit():
        parts = parts[:-1]
    elif parts and re.fullmatch(r".*\d[A-Z]", parts[-1]):
        parts[-1] = parts[-1][:-1]
    if parts and parts[0].startswith("INV") and (parts[0] == "INV" or parts[0][3:4].isdigit()):
        parts[0] = parts[0][3:]
    parts = [re.sub(r"^0+(?=\d)", "", p) for p in parts if p]
    return "".join(parts)


# ---------- dates ----------

_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
                 "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y", "%Y-%m-%d"]


def parse_date_in(s) -> date | None:
    """Indian date formats, always day first. Returns None when it isn't a valid date."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", str(s).strip(), flags=re.I)
    text = re.sub(r"\s+", " ", text.replace(",", " ")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------- units ----------

_UNITS = {
    "kg": ("kg", 1), "kgs": ("kg", 1), "kilogram": ("kg", 1), "kilograms": ("kg", 1),
    "t": ("kg", 1000), "tonne": ("kg", 1000), "tonnes": ("kg", 1000), "mt": ("kg", 1000),
    "ton": ("kg", 1000), "tons": ("kg", 1000),
    "nos": ("pc", 1), "no": ("pc", 1), "pcs": ("pc", 1), "pc": ("pc", 1), "piece": ("pc", 1),
    "pieces": ("pc", 1), "unit": ("pc", 1), "units": ("pc", 1), "ea": ("pc", 1), "each": ("pc", 1),
    "dozen": ("pc", 12), "doz": ("pc", 12),
}


def _unit(u: str) -> tuple[str, int]:
    key = u.strip().lower().rstrip(".")
    if key in _UNITS:
        return _UNITS[key]
    return (key[:-1] if key.endswith("s") and len(key) > 2 else key), 1


def convert_qty(qty: Decimal, from_unit: str | None, to_unit: str | None) -> Decimal | None:
    """Convert a quantity between units. None when the units can't be converted."""
    if not from_unit or not to_unit:
        return Decimal(qty)
    (base_a, fa), (base_b, fb) = _unit(from_unit), _unit(to_unit)
    if base_a != base_b:
        return None
    result = Decimal(qty) * fa / fb
    return result.quantize(Decimal(1)) if result == result.to_integral_value() else result

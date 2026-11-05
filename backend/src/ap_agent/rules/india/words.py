"""Amounts in words, Indian system (crore, lakh, thousand, hundred).

Indian invoices print the total in words as well as figures. Comparing the two catches
typing mistakes on the invoice and digits the reader misread.
"""
import re
from decimal import Decimal

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
_SCALES = [(10_000_000, "Crore"), (100_000, "Lakh"), (1000, "Thousand"), (100, "Hundred")]

_WORD_VALUES = {w.lower(): i for i, w in enumerate(_ONES) if w}
_WORD_VALUES.update({w.lower(): i * 10 for i, w in enumerate(_TENS) if w})
_WORD_VALUES.update({"zero": 0, "fourty": 40, "ninty": 90})
_SCALE_VALUES = {"crore": 10_000_000, "crores": 10_000_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
                 "lacs": 100_000, "thousand": 1000, "hundred": 100}
_FILLER = {"rupees", "rupee", "rs", "inr", "only", "and", "of", "the", "indian"}


def _below_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _int_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for value, name in _SCALES:
        if n >= value:
            count = n // value
            parts.append(f"{_int_words(count) if count >= 100 else _below_100(count)} {name}")
            n %= value
    if n:
        parts.append(_below_100(n))
    return " ".join(parts)


def amount_to_words(amount: Decimal) -> str:
    amount = Decimal(amount).quantize(Decimal("0.01"))
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    text = f"Rupees {_int_words(rupees)}"
    if paise:
        text += f" and {_below_100(paise)} Paise"
    return text + " Only"


def _parse_int(tokens: list[str]) -> int | None:
    total, current, seen = 0, 0, False
    for t in tokens:
        if t in _WORD_VALUES:
            current += _WORD_VALUES[t]
            seen = True
        elif t == "hundred":
            current = (current or 1) * 100
            seen = True
        elif t in _SCALE_VALUES:
            total += (current or 1) * _SCALE_VALUES[t]
            current = 0
            seen = True
        else:
            return None
    return total + current if seen else None


def words_to_amount(text: str | None) -> Decimal | None:
    """Parse an amount written in words. Returns None if the text is not a number in words."""
    if not text:
        return None
    words = re.sub(r"[^a-z ]", " ", text.lower().replace("-", " ")).split()
    if "paise" in words:
        i = words.index("paise")
        head, tail = words[:i], []
        # "... and Fifty Paise": the paise number is the run of number words just before "paise"
        j = len(head)
        while j > 0 and head[j - 1] in _WORD_VALUES:
            j -= 1
        head, tail = head[:j], head[j:]
    else:
        head, tail = words, []
    head = [w for w in head if w not in _FILLER]
    rupees = _parse_int(head) if head else 0
    paise = _parse_int(tail) if tail else 0
    if rupees is None or paise is None or (not head and not tail):
        return None
    return Decimal(rupees) + Decimal(paise) / 100

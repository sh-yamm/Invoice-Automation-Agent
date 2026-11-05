"""GSTIN structure and check digit.

A GSTIN is 15 characters: 2-digit state code, 10-character PAN, entity number, the letter Z,
and a mod-36 check digit computed over the first 14 characters.
"""
import re

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_digit(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        p = _ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return _ALPHABET[(36 - total % 36) % 36]


def is_valid_gstin(g: str | None) -> bool:
    if not g or not _PATTERN.match(g):
        return False
    return gstin_check_digit(g[:14]) == g[14]


def gstin_state(g: str) -> str:
    return g[:2]

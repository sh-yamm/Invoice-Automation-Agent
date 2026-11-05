"""Money helpers. Amounts are Decimal end to end; rounding happens only here."""
from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def to_money(x) -> Decimal:
    """Quantise to paise, rounding half up."""
    return Decimal(str(x)).quantize(PAISE, rounding=ROUND_HALF_UP)


def fmt_inr(amount: Decimal) -> str:
    """Format with Indian digit grouping: ₹1,29,00,000.50."""
    value = to_money(amount)
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{frac}"

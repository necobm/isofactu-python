"""Fixed-point arithmetic helpers.

The original PHP implementation used `bcmath` (`bcmul`, `bcdiv`, `bcadd`, `bcsub`) with an explicit
scale. The helpers below keep the same API and scales but round *half-up* (commercial
rounding, as expected on Spanish invoices) instead of bcmath's truncation.
"""

from decimal import ROUND_HALF_UP, Decimal

Numeric = Decimal | int | str

TWO_PLACES = 2
FOUR_PLACES = 4


def to_decimal(value: Numeric | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # Avoid binary float artefacts (0.1 + 0.2 ...): go through repr().
        return Decimal(repr(value))
    return Decimal(value)


def scale(value: Numeric | float, places: int = TWO_PLACES) -> Decimal:
    """Round `value` half-up to `places` decimals."""
    quantum = Decimal(1).scaleb(-places)
    return to_decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)


def bcmul(a: Numeric, b: Numeric, places: int = TWO_PLACES) -> Decimal:
    return scale(to_decimal(a) * to_decimal(b), places)


def bcdiv(a: Numeric, b: Numeric, places: int = TWO_PLACES) -> Decimal:
    return scale(to_decimal(a) / to_decimal(b), places)


def bcadd(a: Numeric, b: Numeric, places: int = TWO_PLACES) -> Decimal:
    return scale(to_decimal(a) + to_decimal(b), places)


def bcsub(a: Numeric, b: Numeric, places: int = TWO_PLACES) -> Decimal:
    return scale(to_decimal(a) - to_decimal(b), places)

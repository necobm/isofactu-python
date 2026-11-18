"""The tax estimates of a quarter, from the figures of the tenant's invoices.

Estimates, not tax returns: they help a freelancer know what is coming, but they ignore
everything a real return takes into account (non-deductible VAT, prorrata, previous
quarters, pending compensations...).

- **IVA** (VAT): what was charged on the quarter's issued invoices (*repercutido*) minus what
  was paid on its received invoices (*soportado*). Negative: VAT to carry forward.
- **IRPF**: 20 % of the taxable base invoiced to clients outside Spain -- they do not withhold
  IRPF, so the freelancer pays it in advance (the 20 % of modelo 130) -- minus the IRPF that
  clients withheld on the quarter's invoices (already paid on the freelancer's behalf).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Rate of the quarterly IRPF advance payment on income that was not withheld (modelo 130)
IRPF_ADVANCE_RATE = Decimal("20")
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class QuarterFigures:
    """What the tenant's final invoices of the quarter add up to."""

    vat_collected: Decimal  # VAT on issued invoices
    vat_paid: Decimal  # VAT on received invoices
    foreign_income: Decimal  # taxable base of issued invoices to clients outside Spain
    irpf_withheld: Decimal  # IRPF withheld by clients on issued invoices
    issued_count: int
    received_count: int
    foreign_count: int


def vat_estimate(collected: Decimal, paid: Decimal) -> Decimal:
    return collected - paid


def irpf_from_income(foreign_income: Decimal) -> Decimal:
    """20 % of the income clients did not withhold IRPF from, rounded half-up to cents."""
    return (foreign_income * IRPF_ADVANCE_RATE / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def irpf_estimate(from_income: Decimal, withheld: Decimal) -> Decimal:
    return from_income - withheld

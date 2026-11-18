"""API contract of the Taxes module (camelCase JSON, amounts as numbers with two decimals)."""

from datetime import date

from pydantic import Field

from app.core.schemas import ApiModel
from app.invoicing.schemas import Money, Rate


class VatSummary(ApiModel):
    """IVA of the quarter."""

    collected: Money = Field(description="VAT charged on the issued invoices (repercutido)")
    paid: Money = Field(description="VAT paid on the received invoices (soportado)")
    estimated: Money = Field(
        description="collected - paid: what is expected to be paid (negative: to carry forward)"
    )
    issued_count: int = Field(description="Issued invoices of the quarter")
    received_count: int = Field(description="Received invoices of the quarter")


class IrpfSummary(ApiModel):
    """IRPF of the quarter."""

    rate: Rate = Field(description="Advance payment rate on income not withheld (20 %)")
    foreign_income: Money = Field(
        description="Taxable base of the issued invoices to clients outside Spain"
    )
    from_income: Money = Field(description="`rate` % of `foreignIncome`")
    withheld: Money = Field(description="IRPF withheld by clients on the issued invoices")
    estimated: Money = Field(
        description="fromIncome - withheld: what is expected to be paid (negative: nothing)"
    )
    foreign_invoice_count: int = Field(description="Issued invoices to clients outside Spain")


class TaxSummaryRead(ApiModel):
    year: int = Field(examples=[2026])
    quarter: int = Field(ge=1, le=4, examples=[3])
    period_start: date = Field(description="First day of the quarter")
    period_end: date = Field(description="Last day of the quarter (inclusive)")
    vat: VatSummary
    irpf: IrpfSummary

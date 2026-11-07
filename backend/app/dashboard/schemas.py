"""API contract of the dashboard (camelCase JSON, amounts as numbers with two decimals)."""

from datetime import date

from pydantic import Field

from app.core.schemas import ApiModel
from app.invoicing.schemas import Money


class BookTotals(ApiModel):
    """The final invoices of one book (issued = income, received = expenses) in the period."""

    count: int = Field(description="Number of invoices")
    base: Money = Field(description="Taxable base: the income / expense itself, without VAT")
    tax_amount: Money = Field(description="VAT")
    retention_amount: Money = Field(description="IRPF withheld")
    total: Money = Field(description="Invoice totals: base + VAT - IRPF")


class PendingCollection(ApiModel):
    """Issued invoices not collected yet, whatever their date."""

    count: int
    total: Money = Field(description="What the clients owe (invoice totals)")
    overdue_count: int = Field(description="Those past their due date")
    overdue_total: Money


class MonthlyBalance(ApiModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$", examples=["2026-03"])
    income: Money = Field(description="Taxable base of the invoices issued that month")
    expenses: Money = Field(description="Taxable base of the invoices received that month")


class DashboardRead(ApiModel):
    period_start: date = Field(description="First day of the period the figures cover")
    period_end: date = Field(description="Last day of the period (inclusive)")
    income: BookTotals
    expenses: BookTotals
    pending_collection: PendingCollection = Field(
        description="Not limited to the period: everything still to be collected"
    )
    monthly: list[MonthlyBalance] = Field(
        description="One entry per month of the period, months without invoices included"
    )

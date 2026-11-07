"""The dashboard figures, aggregated in the database for one tenant.

Invoice amounts are not stored: the models compute them from the lines (`Invoice.subtotal`,
`.tax_amount`, `.retention_amount`, `.total`). The expressions below do exactly the same in
SQL -- per line ``base = round(quantity * unit_price, 2)`` and
``tax = round(base * round(rate / 100, 4), 2)``, per invoice
``retention = round(base * round(retention_rate / 100, 4), 2)`` -- and PostgreSQL's
``round(numeric)`` breaks ties away from zero like Python's ``ROUND_HALF_UP``, so the totals
match the invoices to the cent (``tests/test_dashboard.py`` checks it).

Only final invoices count (ISSUED; received invoices always are): drafts are not income.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine

ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class Totals:
    count: int = 0
    base: Decimal = ZERO
    tax_amount: Decimal = ZERO
    retention_amount: Decimal = ZERO
    total: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class Pending:
    count: int = 0
    total: Decimal = ZERO
    overdue_count: int = 0
    overdue_total: Decimal = ZERO


_invoice = Invoice.__table__.c
_line = InvoiceLine.__table__.c

_line_base = func.round(_line.quantity * _line.unit_price, 2)
_line_tax = func.round(_line_base * func.round(_line.tax_rate / 100, 4), 2)
_per_invoice = (
    select(
        _line.invoice_id.label("invoice_id"),
        func.sum(_line_base).label("base"),
        func.sum(_line_tax).label("tax"),
    )
    .group_by(_line.invoice_id)
    .subquery("invoice_amounts")
)

# Amounts of one invoice, as columns of `_invoices`
_base = func.coalesce(_per_invoice.c.base, ZERO)
_tax = func.coalesce(_per_invoice.c.tax, ZERO)
_retention = func.round(_base * func.round(_invoice.retention_rate / 100, 4), 2)
_total = _base + _tax - _retention
_invoices = Invoice.__table__.outerjoin(_per_invoice, _per_invoice.c.invoice_id == _invoice.id)


def _sum(expression) -> object:
    return func.coalesce(func.sum(expression), ZERO)


class DashboardRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    def _final(self, query: Select) -> Select:
        return query.select_from(_invoices).where(
            _invoice.owner_id == self.owner_id, _invoice.state == InvoiceState.ISSUED
        )

    async def totals(self, kind: InvoiceKind, start: date, end: date) -> Totals:
        """Final invoices of one book issued within ``[start, end]``."""
        query = self._final(
            select(func.count(), _sum(_base), _sum(_tax), _sum(_retention), _sum(_total))
        ).where(_invoice.kind == kind, _invoice.issue_date.between(start, end))
        row = (await self.session.execute(query)).one()
        return Totals(*row)

    async def monthly_bases(self, start: date, end: date) -> dict[tuple[str, InvoiceKind], Decimal]:
        """Taxable base per (``YYYY-MM`` month, book) within ``[start, end]``; months
        without invoices are missing."""
        month = func.to_char(_invoice.issue_date, "YYYY-MM")
        query = (
            self._final(select(month, _invoice.kind, _sum(_base)))
            .where(_invoice.issue_date.between(start, end))
            .group_by(month, _invoice.kind)
        )
        rows = (await self.session.execute(query)).all()
        return {(m, InvoiceKind(kind)): amount for m, kind, amount in rows}

    async def pending_collection(self, today: date) -> Pending:
        """Issued invoices the client has not paid yet (whatever their date), and those
        of them already past their due date. The amount is what the client owes: the
        invoice total (VAT included, IRPF withheld)."""
        overdue = _invoice.due_date < today
        query = self._final(
            select(
                func.count(),
                _sum(_total),
                func.count().filter(overdue),
                func.coalesce(func.sum(_total).filter(overdue), ZERO),
            )
        ).where(_invoice.kind == InvoiceKind.ISSUED, _invoice.collected_on.is_(None))
        row = (await self.session.execute(query)).one()
        return Pending(*row)

    async def first_issue_date(self) -> date | None:
        """The date of the tenant's oldest final invoice (issued or received)."""
        return await self.session.scalar(self._final(select(func.min(_invoice.issue_date))))

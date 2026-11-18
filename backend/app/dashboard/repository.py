"""The dashboard figures, aggregated in the database for one tenant.

Amounts are computed in SQL exactly like the models compute them (see
``app.invoicing.aggregates``), so the totals match the invoices to the cent. Only final
invoices count (ISSUED; received invoices always are): drafts are not income.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.invoicing import aggregates as amounts
from app.invoicing.aggregates import ZERO
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState


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


class DashboardRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    def _final(self, query: Select) -> Select:
        return query.select_from(amounts.invoices_with_amounts).where(
            amounts.invoice.owner_id == self.owner_id, amounts.invoice.state == InvoiceState.ISSUED
        )

    async def totals(self, kind: InvoiceKind, start: date, end: date) -> Totals:
        """Final invoices of one book issued within ``[start, end]``."""
        query = self._final(
            select(
                func.count(),
                amounts.sum_of(amounts.base),
                amounts.sum_of(amounts.tax),
                amounts.sum_of(amounts.retention),
                amounts.sum_of(amounts.total),
            )
        ).where(amounts.invoice.kind == kind, amounts.invoice.issue_date.between(start, end))
        row = (await self.session.execute(query)).one()
        return Totals(*row)

    async def monthly_bases(self, start: date, end: date) -> dict[tuple[str, InvoiceKind], Decimal]:
        """Taxable base per (``YYYY-MM`` month, book) within ``[start, end]``; months
        without invoices are missing."""
        month = func.to_char(amounts.invoice.issue_date, "YYYY-MM")
        query = (
            self._final(select(month, amounts.invoice.kind, amounts.sum_of(amounts.base)))
            .where(amounts.invoice.issue_date.between(start, end))
            .group_by(month, amounts.invoice.kind)
        )
        rows = (await self.session.execute(query)).all()
        return {(m, InvoiceKind(kind)): amount for m, kind, amount in rows}

    async def pending_collection(self, today: date) -> Pending:
        """Issued invoices the client has not paid yet (whatever their date), and those
        of them already past their due date. The amount is what the client owes: the
        invoice total (VAT included, IRPF withheld)."""
        overdue = amounts.invoice.due_date < today
        query = self._final(
            select(
                func.count(),
                amounts.sum_of(amounts.total),
                func.count().filter(overdue),
                func.coalesce(func.sum(amounts.total).filter(overdue), ZERO),
            )
        ).where(amounts.invoice.kind == InvoiceKind.ISSUED, amounts.invoice.collected_on.is_(None))
        row = (await self.session.execute(query)).one()
        return Pending(*row)

    async def first_issue_date(self) -> date | None:
        """The date of the tenant's oldest final invoice (issued or received)."""
        return await self.session.scalar(self._final(select(func.min(amounts.invoice.issue_date))))

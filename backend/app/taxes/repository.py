"""The figures the tax estimates are computed from, aggregated in the database for one
tenant (with the same per-line rounding as the invoices: ``app.invoicing.aggregates``)."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.invoicing import aggregates as amounts
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Subject
from app.taxes.calculations import QuarterFigures

SPAIN = "ES"
_recipient = Subject.__table__.c


class TaxRepository:
    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        self.session = session
        self.owner_id = owner_id

    async def figures(self, start: date, end: date) -> QuarterFigures:
        """The final invoices (drafts never count) issued within ``[start, end]``. A
        client is foreign when the address of the invoice's copy of it is outside Spain."""
        invoice = amounts.invoice
        issued = invoice.kind == InvoiceKind.ISSUED
        received = invoice.kind == InvoiceKind.RECEIVED
        country = func.upper(func.trim(func.coalesce(_recipient.address_country_iso_code, SPAIN)))
        abroad = issued & (country != SPAIN)
        query = (
            select(
                amounts.sum_of(amounts.tax, where=issued),
                amounts.sum_of(amounts.tax, where=received),
                amounts.sum_of(amounts.base, where=abroad),
                amounts.sum_of(amounts.retention, where=issued),
                func.count().filter(issued),
                func.count().filter(received),
                func.count().filter(abroad),
            )
            .select_from(
                amounts.invoices_with_amounts.join(
                    Subject.__table__, _recipient.id == invoice.recipient_id
                )
            )
            .where(
                invoice.owner_id == self.owner_id,
                invoice.state == InvoiceState.ISSUED,
                invoice.issue_date.between(start, end),
            )
        )
        row = (await self.session.execute(query)).one()
        return QuarterFigures(*row)

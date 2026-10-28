"""Populate a database with generated fixtures (used by the CLI and the tests)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fixtures.factories import InvoiceFactory, SubjectFactory, bind_session, reseed
from app.invoicing.models import Invoice, InvoiceLine, Subject


@dataclass(frozen=True, slots=True)
class LoadReport:
    subjects: int
    invoices: int
    lines: int


async def purge_fixtures(session: AsyncSession) -> None:
    """Delete every invoice, line and subject (in dependency order)."""
    for model in (InvoiceLine, Invoice, Subject):
        await session.execute(delete(model))


async def load_fixtures(
    session: AsyncSession,
    *,
    issuers: int = 1,
    clients: int = 6,
    invoices: int = 20,
    seed: int | None = None,
    purge: bool = False,
) -> LoadReport:
    """Generate `issuers` + `clients` subjects and `invoices` invoices between them.

    The caller owns the transaction: nothing is committed here.
    """
    if seed is not None:
        reseed(seed)
    if purge:
        await purge_fixtures(session)

    with bind_session(session):
        issuer_pool = SubjectFactory.create_batch(issuers)
        client_pool = SubjectFactory.create_batch(clients)
        for index in range(invoices):
            InvoiceFactory(
                issuer=issuer_pool[index % len(issuer_pool)],
                recipient=client_pool[index % len(client_pool)],
            )
        await session.flush()

    count = func.count()
    return LoadReport(
        subjects=await session.scalar(select(count).select_from(Subject)) or 0,
        invoices=await session.scalar(select(count).select_from(Invoice)) or 0,
        lines=await session.scalar(select(count).select_from(InvoiceLine)) or 0,
    )

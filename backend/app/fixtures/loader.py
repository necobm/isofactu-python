"""Populate a database with generated fixtures (used by the CLI and the tests)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import factory
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.accounts.repository import UserRepository
from app.accounts.security import hash_password
from app.clients.models import Client
from app.fixtures.factories import (
    ClientFactory,
    FiscalDataFactory,
    InvoiceFactory,
    ReceivedInvoiceFactory,
    SerialFactory,
    SubjectFactory,
    UserFactory,
    bind_session,
    reseed,
)
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject
from app.invoicing.repository import FiscalDataRepository, InvoiceRepository, SerialRepository

# The tenant owning the generated data, so that it can be browsed after logging in.
DEMO_TENANT_EMAIL = "demo@isofactu.local"
DEMO_TENANT_PASSWORD = "demo1234"
DEMO_TENANT_NAME = "Cuenta de demostración"


@dataclass(frozen=True, slots=True)
class LoadReport:
    clients: int
    invoices: int  # issued ones
    received: int
    lines: int  # of both kinds
    owner: str


# Share of issued invoices older than a few weeks that the client has paid already
COLLECTED_RATIO = 0.8


def _collection_date(issued: dt.date) -> dt.date | None:
    """When the client paid an issued invoice: most older invoices are collected a few
    weeks after their issue date; recent ones (and a few old ones) are still pending."""
    rng = factory.random.randgen
    today = dt.date.today()
    if (today - issued).days < 20 or rng.random() >= COLLECTED_RATIO:
        return None
    return min(today, issued + dt.timedelta(days=rng.randint(5, 45)))


async def purge_fixtures(session: AsyncSession) -> None:
    """Delete every invoice, line, subject, client and serial (in dependency order).
    Accounts and their fiscal data are kept."""
    for model in (InvoiceLine, Invoice, Subject, Client, Serial):
        await session.execute(delete(model))


async def ensure_demo_tenant(session: AsyncSession, *, password_hash_rounds: int = 12) -> User:
    """The demo ADMIN account (created on first use; the password is reset each time so
    that the documented credentials always work)."""
    user = await UserRepository(session).find_by_email(DEMO_TENANT_EMAIL)
    if user is None:
        with bind_session(session):
            user = UserFactory(email=DEMO_TENANT_EMAIL, name=DEMO_TENANT_NAME)
    user.password_hash = hash_password(DEMO_TENANT_PASSWORD, password_hash_rounds)
    await session.flush()
    return user


async def ensure_fiscal_data(session: AsyncSession, owner: User) -> FiscalData:
    """The tenant's fiscal data, generated when it has none yet."""
    data = await FiscalDataRepository(session, owner.id).get()
    if data is None:
        with bind_session(session):
            data = FiscalDataFactory(owner=owner)
        await session.flush()
    return data


async def ensure_serial(session: AsyncSession, owner: User) -> Serial:
    """A serial of the tenant to number the generated invoices with (its first one, or a
    generated ``F-<year>-`` when it has none)."""
    serials = await SerialRepository(session, owner.id).find_all()
    if serials:
        return serials[0]
    with bind_session(session):
        serial = SerialFactory(owner=owner)
    await session.flush()
    return serial


async def load_fixtures(
    session: AsyncSession,
    *,
    owner: User | None = None,
    clients: int = 6,
    invoices: int = 20,
    received: int = 8,
    seed: int | None = None,
    purge: bool = False,
    password_hash_rounds: int = 12,
) -> LoadReport:
    """Generate `clients` clients and `invoices` invoices issued to them (each with its own
    copy of the client as recipient, as the API does), plus `received` invoices from
    generated suppliers (each with its own copy of the fiscal data as recipient), all owned
    by `owner` (the demo tenant when omitted), whose fiscal data and a serial are generated
    too if missing. Issued invoices are numbered correlatively from that serial, in
    issue-date order; received ones carry the supplier's number.

    The caller owns the transaction: nothing is committed here.
    """
    if seed is not None:
        reseed(seed)
    if purge:
        await purge_fixtures(session)
    if owner is None:
        owner = await ensure_demo_tenant(session, password_hash_rounds=password_hash_rounds)
    fiscal_data = await ensure_fiscal_data(session, owner)
    issuer = fiscal_data.as_issuer()
    serial = await ensure_serial(session, owner)
    next_number = await InvoiceRepository(session, owner.id).next_number(serial)

    with bind_session(session):
        client_pool = ClientFactory.create_batch(clients, owner=owner)
        generated = [
            InvoiceFactory(
                owner=owner,
                issuer=issuer,
                recipient=SubjectFactory.copy_of(client_pool[index % len(client_pool)]),
            )
            for index in range(invoices)
        ]
        for invoice in sorted(generated, key=lambda i: i.issue_date):
            invoice.serial_id = serial.id
            if invoice.state is InvoiceState.ISSUED:
                invoice.invoice_number = serial.number(next_number)
                next_number += 1
                invoice.collected_on = _collection_date(invoice.issue_date)
        for _ in range(received):
            ReceivedInvoiceFactory(
                owner=owner, recipient=SubjectFactory.copy_of_account(fiscal_data)
            )
        await session.flush()

    def count_of(kind: InvoiceKind):
        return select(func.count()).select_from(Invoice).where(Invoice.kind == kind)

    count = func.count()
    return LoadReport(
        clients=await session.scalar(select(count).select_from(Client)) or 0,
        invoices=await session.scalar(count_of(InvoiceKind.ISSUED)) or 0,
        received=await session.scalar(count_of(InvoiceKind.RECEIVED)) or 0,
        lines=await session.scalar(select(count).select_from(InvoiceLine)) or 0,
        owner=owner.email,
    )

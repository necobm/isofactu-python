"""Populate a database with generated fixtures (used by the CLI and the tests)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.accounts.repository import UserRepository
from app.accounts.security import hash_password
from app.fixtures.factories import (
    FiscalDataFactory,
    InvoiceFactory,
    SerialFactory,
    SubjectFactory,
    UserFactory,
    bind_session,
    reseed,
)
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject
from app.invoicing.repository import FiscalDataRepository, InvoiceRepository, SerialRepository

# The tenant owning the generated data, so that it can be browsed after logging in.
DEMO_TENANT_EMAIL = "demo@isofactu.local"
DEMO_TENANT_PASSWORD = "demo1234"
DEMO_TENANT_NAME = "Cuenta de demostración"


@dataclass(frozen=True, slots=True)
class LoadReport:
    subjects: int
    invoices: int
    lines: int
    owner: str


async def purge_fixtures(session: AsyncSession) -> None:
    """Delete every invoice, line, subject and serial (in dependency order). Accounts and
    their fiscal data are kept."""
    for model in (InvoiceLine, Invoice, Subject, Serial):
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
    seed: int | None = None,
    purge: bool = False,
    password_hash_rounds: int = 12,
) -> LoadReport:
    """Generate `clients` subjects and `invoices` invoices issued to them, all owned by
    `owner` (the demo tenant when omitted), whose fiscal data and a serial are generated
    too if missing. Issued invoices are numbered correlatively from that serial, in
    issue-date order.

    The caller owns the transaction: nothing is committed here.
    """
    if seed is not None:
        reseed(seed)
    if purge:
        await purge_fixtures(session)
    if owner is None:
        owner = await ensure_demo_tenant(session, password_hash_rounds=password_hash_rounds)
    issuer = (await ensure_fiscal_data(session, owner)).as_issuer()
    serial = await ensure_serial(session, owner)
    next_number = await InvoiceRepository(session, owner.id).next_number(serial)

    with bind_session(session):
        client_pool = SubjectFactory.create_batch(clients, owner=owner)
        generated = [
            InvoiceFactory(
                owner=owner, issuer=issuer, recipient=client_pool[index % len(client_pool)]
            )
            for index in range(invoices)
        ]
        for invoice in sorted(generated, key=lambda i: i.issue_date):
            invoice.serial_id = serial.id
            if invoice.state is InvoiceState.ISSUED:
                invoice.invoice_number = serial.number(next_number)
                next_number += 1
        await session.flush()

    count = func.count()
    return LoadReport(
        subjects=await session.scalar(select(count).select_from(Subject)) or 0,
        invoices=await session.scalar(select(count).select_from(Invoice)) or 0,
        lines=await session.scalar(select(count).select_from(InvoiceLine)) or 0,
        owner=owner.email,
    )

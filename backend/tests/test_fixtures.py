"""Tests for the factory_boy factories, the pytest fixtures built on them and the loader."""

import random
from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.clients.models import Client
from app.fixtures import (
    DEMO_TENANT_EMAIL,
    DEMO_TENANT_PASSWORD,
    InvoiceFactory,
    ReceivedInvoiceFactory,
    SubjectFactory,
    load_fixtures,
    purge_fixtures,
    reseed,
)
from app.fixtures.factories import spanish_cif, spanish_nif
from app.invoicing import spanish_ids
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject
from tests.conftest import login


def test_spanish_identifiers_are_well_formed() -> None:
    rng = random.Random(7)
    for _ in range(200):
        nif = spanish_nif(rng)
        assert len(nif) == 9 and nif[:8].isdigit()
        assert nif[8] == spanish_ids.NIF_CONTROL[int(nif[:8]) % 23]
        assert spanish_ids.is_valid_nif(nif)

        cif = spanish_cif(rng)
        assert len(cif) == 9 and cif[0].isalpha() and cif[1:8].isdigit()
        assert spanish_ids.is_valid_cif(cif)


def test_build_does_not_need_a_session() -> None:
    reseed(1)
    invoice = InvoiceFactory.build(lines=2)
    assert invoice.id is None
    assert len(invoice.lines) == 2
    # Generated data satisfies the API rules: a concept on every line and a positive amount
    assert all(line.description for line in invoice.lines)
    assert invoice.subtotal > 0
    # The issuer is a generated company snapshot; the recipient belongs to the invoice's tenant
    assert invoice.issuer.full_name and invoice.issuer.document.number
    assert invoice.owner is invoice.recipient.owner
    lines_total = sum((line.total for line in invoice.lines), Decimal("0.00"))
    assert invoice.total == lines_total - invoice.retention_amount
    assert all(line.invoice is invoice for line in invoice.lines)


def test_reseed_makes_data_reproducible() -> None:
    reseed(99)
    first = SubjectFactory.build()
    reseed(99)
    second = SubjectFactory.build()
    assert (first.full_name, first.document, first.address) == (
        second.full_name,
        second.document,
        second.address,
    )


def test_subject_factory_respects_document_type() -> None:
    reseed(3)
    company = SubjectFactory.build(document__type=DocumentType.CIF)
    assert company.document.type is DocumentType.CIF
    assert company.document.number[0].isalpha()

    person = SubjectFactory.build(document__type=DocumentType.NIF, full_name="Ana")
    assert person.full_name == "Ana"
    assert person.document.number[:8].isdigit()


def test_invoice_factory_generates_both_states() -> None:
    reseed(11)
    invoices = [InvoiceFactory.build(lines=1) for _ in range(50)]
    assert {i.state for i in invoices} == {InvoiceState.DRAFT, InvoiceState.ISSUED}
    # Drafts are numberless, issued invoices are numbered
    assert all(i.invoice_number.is_assigned == (i.state is InvoiceState.ISSUED) for i in invoices)

    pinned = InvoiceFactory.build(lines=1, state=InvoiceState.ISSUED)
    assert pinned.state is InvoiceState.ISSUED
    assert pinned.invoice_number.is_assigned
    assert pinned.due_date == pinned.issue_date + timedelta(days=30)
    assert not InvoiceFactory.build(lines=1, state=InvoiceState.DRAFT).invoice_number.is_assigned


def test_received_invoice_factory() -> None:
    reseed(3)
    invoices = ReceivedInvoiceFactory.build_batch(20)
    assert {invoice.kind for invoice in invoices} == {InvoiceKind.RECEIVED}
    assert {invoice.serial_id for invoice in invoices} == {None}
    # No drafts: every received invoice is stored as issued (by its supplier), numbered
    assert {invoice.state for invoice in invoices} == {InvoiceState.ISSUED}
    for invoice in invoices:
        assert invoice.invoice_number.is_assigned
        assert invoice.lines and all(line.description for line in invoice.lines)


async def test_invoice_fixture_is_persisted(
    invoice: Invoice, tenant: User, session: AsyncSession
) -> None:
    assert invoice.id is not None
    assert invoice.owner_id == tenant.id
    assert invoice.lines and all(line.id is not None for line in invoice.lines)
    assert await session.scalar(select(func.count()).select_from(Subject)) == 1  # the recipient


async def test_factories_feed_the_api(
    tenant_client: AsyncClient,
    invoice_factory: type[InvoiceFactory],
    tenant: User,
    subject: Subject,
) -> None:
    invoice_factory.create_batch(3, owner=tenant, recipient=subject, lines=1)
    invoice_factory(owner=tenant, lines=2)  # pending objects are flushed by the API query
    invoice_factory(lines=1)  # belongs to a generated tenant: invisible to `tenant`

    response = await tenant_client.get("/api/invoice")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert sum(len(item["lines"]) for item in body["items"]) == 5
    assert {item["recipient"]["id"] for item in body["items"]} >= {subject.id}


async def test_load_fixtures_and_purge(session: AsyncSession, client: AsyncClient) -> None:
    report = await load_fixtures(
        session, clients=3, invoices=7, received=4, seed=5, password_hash_rounds=4
    )
    assert (report.clients, report.invoices, report.received) == (3, 7, 4)
    assert report.lines >= 11
    assert report.owner == DEMO_TENANT_EMAIL

    # Every issued invoice is issued by the demo tenant's (generated) fiscal data, and every
    # received one is addressed to it (by a generated supplier)
    fiscal = await session.scalar(select(FiscalData))
    assert fiscal is not None
    columns = Invoice.__table__.c
    issuers = await session.scalars(
        select(columns.issuer_document_number).where(columns.kind == InvoiceKind.ISSUED).distinct()
    )
    assert list(issuers) == [fiscal.document.number]
    received = (
        await session.scalars(select(Invoice).where(Invoice.kind == InvoiceKind.RECEIVED))
    ).unique()
    for invoice in received:
        assert invoice.recipient.document == fiscal.document
        assert invoice.issuer.document_number != fiscal.document.number
        assert invoice.serial_id is None

    # Everything belongs to the demo tenant, which can log in with the documented password
    owners = await session.scalars(select(Invoice.owner_id).distinct())
    demo = await session.scalar(select(User).where(User.email == DEMO_TENANT_EMAIL))
    assert demo is not None and list(owners) == [demo.id]
    await login(client, demo, DEMO_TENANT_PASSWORD)
    assert (await client.get("/api/invoice")).json()["total"] == 7
    assert (await client.get("/api/received-invoice")).json()["total"] == 4

    # Issued invoices are numbered correlatively, in issue-date order, from one serial
    serials = (await client.get("/api/serial")).json()
    assert len(serials) == 1
    issued = (await client.get("/api/invoice", params={"state": "ISSUED", "limit": 200})).json()
    by_date = sorted(issued["items"], key=lambda i: (i["issueDate"], i["id"]))
    numbers = [int(i["invoiceNumber"]["number"]) for i in by_date]
    assert numbers == list(range(1, len(numbers) + 1))
    assert all(i["serialId"] == serials[0]["id"] for i in issued["items"])
    assert serials[0]["issuedCount"] == len(numbers)
    assert serials[0]["nextNumber"] == len(numbers) + 1

    # Loading again reuses the account and only replaces the invoicing data
    report = await load_fixtures(
        session, invoices=2, clients=1, received=1, seed=5, purge=True, password_hash_rounds=4
    )
    assert (report.clients, report.invoices, report.received) == (1, 2, 1)
    assert await session.scalar(select(func.count()).select_from(User)) == 1
    assert await session.scalar(select(func.count()).select_from(FiscalData)) == 1  # reused
    assert await session.scalar(select(func.count()).select_from(Serial)) == 1  # regenerated

    await purge_fixtures(session)
    assert await session.scalar(select(func.count()).select_from(InvoiceLine)) == 0
    assert await session.scalar(select(func.count()).select_from(Subject)) == 0
    assert await session.scalar(select(func.count()).select_from(Client)) == 0
    assert await session.scalar(select(func.count()).select_from(User)) == 1  # accounts stay

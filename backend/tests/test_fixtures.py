"""Tests for the factory_boy factories, the pytest fixtures built on them and the loader."""

import random
from datetime import timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fixtures import InvoiceFactory, SubjectFactory, load_fixtures, purge_fixtures, reseed
from app.fixtures.factories import NIF_CONTROL, spanish_cif, spanish_nif
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine, Subject


def test_spanish_identifiers_are_well_formed() -> None:
    rng = random.Random(7)
    for _ in range(200):
        nif = spanish_nif(rng)
        assert len(nif) == 9 and nif[:8].isdigit()
        assert nif[8] == NIF_CONTROL[int(nif[:8]) % 23]

        cif = spanish_cif(rng)
        assert len(cif) == 9 and cif[0].isalpha() and cif[1:8].isdigit()


def test_build_does_not_need_a_session() -> None:
    reseed(1)
    invoice = InvoiceFactory.build(lines=2)
    assert invoice.id is None
    assert len(invoice.lines) == 2
    # Generated data satisfies the API rules: a concept on every line and a positive amount
    assert all(line.description for line in invoice.lines)
    assert invoice.subtotal > 0
    assert invoice.issuer is not invoice.recipient
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


async def test_invoice_fixture_is_persisted(invoice: Invoice, session: AsyncSession) -> None:
    assert invoice.id is not None
    assert invoice.lines and all(line.id is not None for line in invoice.lines)
    assert await session.scalar(select(func.count()).select_from(Subject)) == 2


async def test_factories_feed_the_api(
    client: AsyncClient, invoice_factory: type[InvoiceFactory], subject: Subject
) -> None:
    invoice_factory.create_batch(3, recipient=subject, lines=1)
    invoice_factory(lines=2)  # pending objects are flushed by the API query

    response = await client.get("/api/invoice")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert sum(len(item["lines"]) for item in body["items"]) == 5
    assert {item["recipient"]["id"] for item in body["items"]} >= {subject.id}


async def test_load_fixtures_and_purge(session: AsyncSession) -> None:
    report = await load_fixtures(session, issuers=2, clients=3, invoices=7, seed=5)
    assert (report.subjects, report.invoices) == (5, 7)
    assert report.lines >= 7

    issuers = await session.scalars(select(Invoice.issuer_id).distinct())
    assert len(list(issuers)) == 2

    report = await load_fixtures(session, invoices=2, clients=1, seed=5, purge=True)
    assert (report.subjects, report.invoices) == (2, 2)

    await purge_fixtures(session)
    assert await session.scalar(select(func.count()).select_from(InvoiceLine)) == 0
    assert await session.scalar(select(func.count()).select_from(Subject)) == 0

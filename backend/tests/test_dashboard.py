"""The dashboard (`GET /api/dashboard`) and collecting issued invoices
(`PUT /api/invoice/{id}/collection`)."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import InvoiceFactory, ReceivedInvoiceFactory
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Invoice, InvoiceLine

TODAY = date.today()
D = Decimal


def line(quantity: str, unit_price: str, tax_rate: str = "21") -> InvoiceLine:
    return InvoiceLine(
        description="Concepto", quantity=D(quantity), unit_price=D(unit_price), tax_rate=D(tax_rate)
    )


@pytest.fixture
def issued(invoice_factory: type[InvoiceFactory], tenant: User):
    """An issued invoice of `tenant` (final unless `state` says otherwise)."""

    def make(day: date, *lines: InvoiceLine, **fields) -> Invoice:
        fields.setdefault("state", InvoiceState.ISSUED)
        fields.setdefault("retention_rate", D(0))
        fields.setdefault("due_date", None)
        return invoice_factory(owner=tenant, issue_date=day, lines=list(lines), **fields)

    return make


@pytest.fixture
def received(received_invoice_factory: type[ReceivedInvoiceFactory], tenant: User):
    def make(day: date, *lines: InvoiceLine, **fields) -> Invoice:
        fields.setdefault("retention_rate", D(0))
        return received_invoice_factory(owner=tenant, issue_date=day, lines=list(lines), **fields)

    return make


async def _dashboard(client: AsyncClient, **params) -> dict:
    response = await client.get("/api/dashboard", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_empty_account(tenant_client: AsyncClient) -> None:
    body = await _dashboard(tenant_client)
    zeros = {"count": 0, "base": 0, "taxAmount": 0, "retentionAmount": 0, "total": 0}
    assert body == {
        "periodStart": TODAY.isoformat(),
        "periodEnd": TODAY.isoformat(),
        "income": zeros,
        "expenses": zeros,
        "pendingCollection": {"count": 0, "total": 0, "overdueCount": 0, "overdueTotal": 0},
        "monthly": [{"month": TODAY.strftime("%Y-%m"), "income": 0, "expenses": 0}],
    }


async def test_income_and_expenses_of_a_period(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    # January: 1000 at 21 % with 15 % IRPF, and 99.99 at 21 % (rounding: tax 20.9979 -> 21.00)
    issued(date(2025, 1, 10), line("10", "100"), retention_rate=D(15))
    issued(date(2025, 1, 31), line("1", "99.99"))
    # March: 250 at 10 %, and a discount line
    issued(date(2025, 3, 3), line("2", "150", "10"), line("1", "-50", "10"))
    # Not income: a draft, and invoices outside the period
    issued(date(2025, 2, 1), line("1", "5000"), state=InvoiceState.DRAFT)
    issued(date(2024, 12, 31), line("1", "777"))
    issued(date(2025, 4, 1), line("1", "888"))
    # Expenses: February rent with 19 % IRPF, March supplies at 21 % and exempt
    received(date(2025, 2, 5), line("1", "600"), retention_rate=D(19))
    received(date(2025, 3, 20), line("3", "10.50"), line("1", "12", "0"))
    await session.flush()

    body = await _dashboard(tenant_client, **{"from": "2025-01-01", "to": "2025-03-31"})
    assert (body["periodStart"], body["periodEnd"]) == ("2025-01-01", "2025-03-31")
    assert body["income"] == {
        "count": 3,
        "base": 1349.99,  # 1000 + 99.99 + 250
        "taxAmount": 256.0,  # 210 + 21 + 25
        "retentionAmount": 150.0,
        "total": 1455.99,
    }
    assert body["expenses"] == {
        "count": 2,
        "base": 643.5,  # 600 + 31.50 + 12
        "taxAmount": 132.62,  # 126 + 6.615 -> 6.62
        "retentionAmount": 114.0,
        "total": 662.12,
    }
    assert body["monthly"] == [
        {"month": "2025-01", "income": 1099.99, "expenses": 0},
        {"month": "2025-02", "income": 0, "expenses": 600.0},  # the draft does not count
        {"month": "2025-03", "income": 250.0, "expenses": 43.5},
    ]

    # A single day, and the default period: from the first invoice up to today
    day = await _dashboard(tenant_client, **{"from": "2025-01-31", "to": "2025-01-31"})
    assert (day["income"]["count"], day["income"]["base"]) == (1, 99.99)
    everything = await _dashboard(tenant_client)
    assert (everything["periodStart"], everything["periodEnd"]) == ("2024-12-31", TODAY.isoformat())
    assert everything["income"]["count"] == 5
    assert everything["monthly"][0] == {"month": "2024-12", "income": 777.0, "expenses": 0}
    assert everything["monthly"][-1]["month"] == TODAY.strftime("%Y-%m")


async def test_totals_match_the_invoices_to_the_cent(
    tenant_client: AsyncClient,
    session: AsyncSession,
    invoice_factory: type[InvoiceFactory],
    received_invoice_factory: type[ReceivedInvoiceFactory],
    tenant: User,
) -> None:
    """The SQL aggregation gives exactly what the models compute, rounding included."""
    rng = random.Random(7)

    def random_lines() -> list[InvoiceLine]:
        return [
            line(
                str(D(rng.randint(1, 2000)) / 100),
                str(D(rng.randint(-5000, 90000)) / 100),  # discounts too
                rng.choice(["21", "10", "4", "0", "7", "5.5"]),
            )
            for _ in range(rng.randint(1, 5))
        ]

    for _ in range(60):
        factory = rng.choice([invoice_factory, received_invoice_factory])
        factory(
            owner=tenant,
            issue_date=date(2025, 1, 1) + timedelta(days=rng.randint(0, 364)),
            lines=random_lines(),
            retention_rate=D(rng.choice(["0", "7", "15", "19", "12.5"])),
        )
    await session.flush()
    invoices = (await session.scalars(select(Invoice))).unique().all()

    def expected(kind: InvoiceKind) -> dict:
        booked = [i for i in invoices if i.kind is kind and i.state is InvoiceState.ISSUED]
        return {
            "count": len(booked),
            "base": float(sum((i.subtotal for i in booked), D(0))),
            "taxAmount": float(sum((i.tax_amount for i in booked), D(0))),
            "retentionAmount": float(sum((i.retention_amount for i in booked), D(0))),
            "total": float(sum((i.total for i in booked), D(0))),
        }

    body = await _dashboard(tenant_client, **{"from": "2025-01-01", "to": "2025-12-31"})
    assert body["income"] == expected(InvoiceKind.ISSUED)
    assert body["expenses"] == expected(InvoiceKind.RECEIVED)
    for point in body["monthly"]:
        month = [i for i in invoices if i.issue_date.strftime("%Y-%m") == point["month"]]
        for kind, key in ((InvoiceKind.ISSUED, "income"), (InvoiceKind.RECEIVED, "expenses")):
            booked = [i for i in month if i.kind is kind and i.state is InvoiceState.ISSUED]
            assert point[key] == float(sum((i.subtotal for i in booked), D(0))), point


async def test_pending_collection(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    old = TODAY - timedelta(days=90)
    # Pending: one overdue (121 + 12.10), one not due yet (100 - 15 % IRPF = 106), one
    # without due date (never overdue)
    a = issued(old, line("1", "100"), due_date=TODAY - timedelta(days=1))
    b = issued(old, line("1", "10"), due_date=TODAY - timedelta(days=60))
    issued(old, line("1", "100"), retention_rate=D(15), due_date=TODAY)
    issued(old, line("1", "50"))
    # Not pending: collected, a draft, and an expense
    issued(old, line("1", "999"), collected_on=old + timedelta(days=5))
    issued(old, line("1", "999"), state=InvoiceState.DRAFT, due_date=old)
    received(old, line("1", "999"))
    await session.flush()

    # Whatever the period: what is owed does not depend on when it was invoiced
    for params in ({}, {"from": TODAY.isoformat(), "to": TODAY.isoformat()}):
        body = await _dashboard(tenant_client, **params)
        assert body["pendingCollection"] == {
            "count": 4,
            "total": 121 + 12.1 + 106 + 60.5,
            "overdueCount": 2,
            "overdueTotal": 133.1,
        }

    # Collecting one of them (through the API) takes it off
    response = await tenant_client.put(
        f"/api/invoice/{a.id}/collection", json={"collectedOn": TODAY.isoformat()}
    )
    assert response.status_code == 200, response.text
    assert response.json()["collectedOn"] == TODAY.isoformat()
    pending = (await _dashboard(tenant_client))["pendingCollection"]
    assert (pending["count"], pending["overdueCount"], pending["overdueTotal"]) == (3, 1, 12.1)

    # ... and marking it pending again puts it back
    await tenant_client.put(f"/api/invoice/{a.id}/collection", json={"collectedOn": None})
    assert (await _dashboard(tenant_client))["pendingCollection"]["count"] == 4
    assert b.collected_on is None


async def test_collecting_an_invoice(
    tenant_client: AsyncClient, session: AsyncSession, issued, received
) -> None:
    day = TODAY - timedelta(days=30)
    invoice = issued(day, line("1", "100"))
    draft = issued(day, line("1", "100"), state=InvoiceState.DRAFT)
    expense = received(day, line("1", "100"))
    await session.flush()
    path = f"/api/invoice/{invoice.id}/collection"

    assert (await tenant_client.get(f"/api/invoice/{invoice.id}")).json()["collectedOn"] is None
    ok = await tenant_client.put(path, json={"collectedOn": day.isoformat()})  # same day: fine
    assert (ok.status_code, ok.json()["collectedOn"]) == (200, day.isoformat())
    listed = (await tenant_client.get("/api/invoice", params={"state": "ISSUED"})).json()
    assert listed["items"][0]["collectedOn"] == day.isoformat()

    async def refused(payload: dict, target: str = path) -> int:
        response = await tenant_client.put(target, json=payload)
        return response.status_code

    assert await refused({"collectedOn": (day - timedelta(days=1)).isoformat()}) == 422
    assert await refused({"collectedOn": (TODAY + timedelta(days=1)).isoformat()}) == 422
    assert await refused({}) == 422  # explicit: a date, or null
    draft_path = f"/api/invoice/{draft.id}/collection"
    assert await refused({"collectedOn": day.isoformat()}, draft_path) == 409
    # Received invoices are not in the issued book
    assert await refused({"collectedOn": None}, f"/api/invoice/{expense.id}/collection") == 404
    assert (await tenant_client.get(f"/api/received-invoice/{expense.id}")).json()[
        "collectedOn"
    ] is None


async def test_the_dashboard_is_per_tenant(
    tenant_client: AsyncClient,
    session: AsyncSession,
    invoice_factory: type[InvoiceFactory],
    other_tenant: User,
    issued,
) -> None:
    issued(TODAY, line("1", "100"), due_date=TODAY - timedelta(days=1))
    theirs = invoice_factory(
        owner=other_tenant,
        state=InvoiceState.ISSUED,
        issue_date=TODAY - timedelta(days=400),
        due_date=TODAY - timedelta(days=1),
        lines=[line("1", "5000")],
    )
    await session.flush()

    body = await _dashboard(tenant_client)
    assert body["periodStart"] == TODAY.isoformat()  # their older invoice is not "the first"
    assert (body["income"]["count"], body["income"]["base"]) == (1, 100.0)
    assert body["pendingCollection"]["count"] == 1
    # Nor can their invoices be collected
    response = await tenant_client.put(
        f"/api/invoice/{theirs.id}/collection", json={"collectedOn": TODAY.isoformat()}
    )
    assert response.status_code == 404


async def test_dashboard_access_and_validation(
    tenant_client: AsyncClient, client: AsyncClient, super_admin_client: AsyncClient
) -> None:
    assert (await client.get("/api/dashboard")).status_code == 401
    assert (await super_admin_client.get("/api/dashboard")).status_code == 403

    async def rejected(params: dict) -> str:
        response = await tenant_client.get("/api/dashboard", params=params)
        assert response.status_code == 422, response.text
        return response.json()["detail"][0]["msg"]

    assert "later than" in await rejected({"from": "2025-02-01", "to": "2025-01-31"})
    assert "240 months" in await rejected({"from": "1990-01-01", "to": "2025-01-31"})
    wrong_format = await tenant_client.get("/api/dashboard", params={"from": "31/01/2025"})
    assert wrong_format.status_code == 422


async def test_the_database_guards_collection_dates(
    session: AsyncSession, issued, received
) -> None:
    day = TODAY - timedelta(days=10)
    issued(day, line("1", "1"), collected_on=day - timedelta(days=1))
    with pytest.raises(IntegrityError, match="ck_invoice_collected_after_issue"):
        await session.flush()
    await session.rollback()

    issued(day, line("1", "1"), state=InvoiceState.DRAFT, collected_on=day)
    with pytest.raises(IntegrityError, match="ck_invoice_collected_when_issued"):
        await session.flush()
    await session.rollback()

    received(day, line("1", "1"), collected_on=day)
    with pytest.raises(IntegrityError, match="ck_invoice_collected_when_issued"):
        await session.flush()

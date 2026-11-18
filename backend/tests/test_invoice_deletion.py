"""Deleting invoices: drafts (`DELETE /api/invoice/{id}`) and received invoices
(`DELETE /api/received-invoice/{id}`). Issued invoices cannot be deleted."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import InvoiceFactory, ReceivedInvoiceFactory
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Invoice, InvoiceLine, Serial, Subject

CLIENT = {
    "fullName": "Tech Solutions SL",
    "document": {"type": "CIF", "number": "B12345674"},
    "address": {
        "street": "Gran Vía 2",
        "zipCode": "48001",
        "city": "Bilbao",
        "province": "Vizcaya",
        "countryIsoCode": "ES",
    },
}
SUPPLIER = {**CLIENT, "fullName": "Suministros Canarios SL"}
LINES = [
    {"description": "Consultoría", "quantity": 1, "unitPrice": 100, "taxRate": 21},
    {"description": "Soporte", "quantity": 2, "unitPrice": 50, "taxRate": 21},
]


@pytest.fixture
def client(tenant_client: AsyncClient, fiscal_data: FiscalData, serial: Serial) -> AsyncClient:
    """A tenant with fiscal data and a `F-2026-` serial."""
    return tenant_client


async def _client_id(client: AsyncClient) -> int:
    response = await client.post("/api/client", json=CLIENT)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _issued_invoice(client: AsyncClient, serial: Serial, state: str) -> dict:
    payload = {
        "state": state,
        "serialId": serial.id,
        "clientId": await _client_id(client),
        "lines": LINES,
    }
    response = await client.post("/api/invoice", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _received_invoice(client: AsyncClient) -> dict:
    payload = {"issuer": SUPPLIER, "invoiceNumber": {"number": "FV-0042"}, "lines": LINES}
    response = await client.post("/api/received-invoice", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _count(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_delete_a_draft(client: AsyncClient, serial: Serial, session: AsyncSession) -> None:
    draft = await _issued_invoice(client, serial, "DRAFT")

    response = await client.delete(f"/api/invoice/{draft['id']}")

    assert response.status_code == 204
    assert (await client.get(f"/api/invoice/{draft['id']}")).status_code == 404
    assert (await client.get("/api/invoice")).json()["total"] == 0
    # Its lines and its copy of the client go with it; the client itself stays
    assert await _count(session, Invoice) == 0
    assert await _count(session, InvoiceLine) == 0
    assert await _count(session, Subject) == 0
    assert (await client.get("/api/client")).json()["total"] == 1
    # Deleting it again: it is gone
    assert (await client.delete(f"/api/invoice/{draft['id']}")).status_code == 404


async def test_issued_invoices_cannot_be_deleted(
    client: AsyncClient, serial: Serial, session: AsyncSession
) -> None:
    issued = await _issued_invoice(client, serial, "ISSUED")

    response = await client.delete(f"/api/invoice/{issued['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "An issued invoice cannot be deleted"
    assert (await client.get(f"/api/invoice/{issued['id']}")).json() == issued
    assert await _count(session, InvoiceLine) == 2


async def test_deleting_a_draft_leaves_the_numbering_alone(
    client: AsyncClient, serial: Serial
) -> None:
    first = await _issued_invoice(client, serial, "ISSUED")
    draft = await _issued_invoice(client, serial, "DRAFT")  # remembers the serial
    assert (await client.delete(f"/api/invoice/{draft['id']}")).status_code == 204

    second = await _issued_invoice(client, serial, "ISSUED")

    assert [first["invoiceNumber"]["number"], second["invoiceNumber"]["number"]] == ["1", "2"]
    serials = (await client.get("/api/serial")).json()
    assert (serials[0]["issuedCount"], serials[0]["nextNumber"]) == (2, 3)


async def test_delete_a_received_invoice(client: AsyncClient, session: AsyncSession) -> None:
    received = await _received_invoice(client)

    response = await client.delete(f"/api/received-invoice/{received['id']}")

    assert response.status_code == 204
    assert (await client.get(f"/api/received-invoice/{received['id']}")).status_code == 404
    assert (await client.get("/api/received-invoice")).json()["total"] == 0
    # Its lines and its copy of the fiscal data (the recipient) go with it
    assert await _count(session, Invoice) == 0
    assert await _count(session, InvoiceLine) == 0
    assert await _count(session, Subject) == 0
    assert (await client.get("/api/fiscal-data")).json()["companyName"] == "Jesús Freelance"


async def test_deleted_received_invoices_stop_counting_as_expenses(client: AsyncClient) -> None:
    kept = await _received_invoice(client)
    deleted = await _received_invoice(client)  # e.g. recorded twice by mistake
    before = (await client.get("/api/dashboard")).json()

    assert (await client.delete(f"/api/received-invoice/{deleted['id']}")).status_code == 204

    after = (await client.get("/api/dashboard")).json()
    assert after["expenses"]["count"] == before["expenses"]["count"] - 1 == 1
    assert after["expenses"]["base"] == kept["subtotal"]


async def test_each_book_deletes_only_its_own_invoices(client: AsyncClient, serial: Serial) -> None:
    draft = await _issued_invoice(client, serial, "DRAFT")
    received = await _received_invoice(client)

    assert (await client.delete(f"/api/received-invoice/{draft['id']}")).status_code == 404
    assert (await client.delete(f"/api/invoice/{received['id']}")).status_code == 404
    assert (await client.get(f"/api/invoice/{draft['id']}")).status_code == 200
    assert (await client.get(f"/api/received-invoice/{received['id']}")).status_code == 200


async def test_tenants_cannot_delete_each_others_invoices(
    client: AsyncClient, session: AsyncSession, other_tenant: User
) -> None:
    draft = InvoiceFactory(owner=other_tenant, state=InvoiceState.DRAFT)
    received = ReceivedInvoiceFactory(owner=other_tenant)
    await session.flush()

    assert (await client.delete(f"/api/invoice/{draft.id}")).status_code == 404
    assert (await client.delete(f"/api/received-invoice/{received.id}")).status_code == 404
    assert await _count(session, Invoice) == 2


async def test_a_recipient_shared_with_other_invoices_is_kept(
    client: AsyncClient, session: AsyncSession, tenant: User, subject: Subject
) -> None:
    """Legacy data: invoices created before clients were copied per invoice may share one
    recipient. Deleting one of them must not take the others' recipient away."""
    draft = InvoiceFactory(owner=tenant, recipient=subject, state=InvoiceState.DRAFT)
    issued = InvoiceFactory(owner=tenant, recipient=subject, state=InvoiceState.ISSUED)
    await session.flush()

    assert (await client.delete(f"/api/invoice/{draft.id}")).status_code == 204

    body = (await client.get(f"/api/invoice/{issued.id}")).json()
    assert body["recipient"]["id"] == subject.id
    assert await _count(session, Subject) == 1


async def test_deleting_requires_a_tenant(
    client: AsyncClient, super_admin_client: AsyncClient, serial: Serial
) -> None:
    draft = await _issued_invoice(client, serial, "DRAFT")

    assert (await super_admin_client.delete(f"/api/invoice/{draft['id']}")).status_code == 403
    await client.post("/api/auth/logout")
    assert (await client.delete(f"/api/invoice/{draft['id']}")).status_code == 401

"""Received invoices (expenses): `/api/received-invoice`.

They work like issued invoices (lines, VAT, IRPF, dates, payment, notes) except that the
supplier (issuer) and its invoice number are entered by hand, the recipient is the account's
own fiscal data, and there is no lifecycle: no drafts, always stored as ISSUED (by the
supplier) and always editable.
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import ReceivedInvoiceFactory
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Serial

SUPPLIER = {
    "fullName": "Suministros Canarios SL",
    "document": {"type": "CIF", "number": "b-1234567-4"},  # normalised by the server
    "address": {
        "street": "Calle Triana 10",
        "zipCode": "35002",
        "city": "Las Palmas de Gran Canaria",
        "province": "Las Palmas",
        "countryIsoCode": "ES",
    },
}
LINE = {"description": "Material de oficina", "quantity": 2, "unitPrice": 50, "taxRate": 7}
NUMBER = {"prefix": "A-", "number": "0042"}
TODAY = date.today()


@pytest.fixture
def client(tenant_client: AsyncClient, fiscal_data: FiscalData) -> AsyncClient:
    """A logged-in tenant with its fiscal data (the recipient of its received invoices)."""
    return tenant_client


def _payload(**extra) -> dict:
    return {"issuer": SUPPLIER, "invoiceNumber": NUMBER, "lines": [LINE], **extra}


async def _create(client: AsyncClient, **extra) -> dict:
    response = await client.post("/api/received-invoice", json=_payload(**extra))
    assert response.status_code == 201, response.text
    return response.json()


async def test_record_a_received_invoice(client: AsyncClient) -> None:
    issue_date = TODAY - timedelta(days=10)
    body = await _create(
        client,
        issueDate=issue_date.isoformat(),
        dueDate=(issue_date + timedelta(days=30)).isoformat(),
        paymentMethod="DIRECT_DEBIT",
        retentionRate=15,
        notes="Factura de marzo",
        lines=[LINE, {"description": "Tóner", "quantity": 1, "unitPrice": 100, "taxRate": 21}],
    )

    # No lifecycle: stored as issued (by the supplier) straight away
    assert (body["kind"], body["state"], body["serialId"]) == ("RECEIVED", "ISSUED", None)
    # The number is the supplier's, as entered
    assert body["invoiceNumber"] == {
        "prefix": "A-",
        "number": "0042",
        "suffix": "",
        "formatted": "A-0042",
    }
    # The issuer is the supplier as entered (document normalised) ...
    assert body["issuer"]["fullName"] == "Suministros Canarios SL"
    assert body["issuer"]["document"] == {"type": "CIF", "number": "B12345674"}
    assert body["issuer"]["address"]["city"] == "Las Palmas de Gran Canaria"
    # ... and the recipient is the account's fiscal data, stamped by the server
    assert body["recipient"]["fullName"] == "Néstor Freelance"
    assert body["recipient"]["document"] == {"type": "NIF", "number": "12345678Z"}
    assert body["recipient"]["address"]["street"] == "Calle Luna 5"
    # Same amounts as any invoice: per-line VAT, IRPF on the subtotal deducted from the total
    assert (body["subtotal"], body["taxAmount"], body["retentionAmount"], body["total"]) == (
        200.0,
        28.0,
        30.0,
        198.0,
    )
    assert (body["paymentMethod"], body["notes"]) == ("DIRECT_DEBIT", "Factura de marzo")

    listed = (await client.get("/api/received-invoice")).json()
    assert (listed["total"], [i["id"] for i in listed["items"]]) == (1, [body["id"]])
    assert (await client.get(f"/api/received-invoice/{body['id']}")).json() == body
    assert (await client.get("/api/received-invoice/999")).status_code == 404


async def test_there_are_no_received_drafts(client: AsyncClient) -> None:
    # A `state` in the payload is not part of the contract: it is ignored
    body = await _create(client, state="DRAFT")
    assert body["state"] == "ISSUED"
    edited = await client.put(f"/api/received-invoice/{body['id']}", json=_payload(state="DRAFT"))
    assert edited.json()["state"] == "ISSUED"


async def test_the_supplier_number_is_always_required(client: AsyncClient) -> None:
    async def rejected(payload: dict, method: str = "POST", path: str = "/api/received-invoice"):
        response = await client.request(method, path, json=payload)
        assert response.status_code == 422, response.text
        return response.json()["detail"][0]["loc"]

    without_number = _payload()
    del without_number["invoiceNumber"]
    assert await rejected(without_number) == ["body", "invoiceNumber"]
    assert await rejected(_payload(invoiceNumber=None)) == ["body", "invoiceNumber"]
    # A blank number counts as missing; a series alone is not a number
    blank = _payload(invoiceNumber={"prefix": "A-", "number": "  "})
    assert await rejected(blank) == ["body", "invoiceNumber", "number"]
    assert await rejected(_payload(invoiceNumber={"prefix": "A-"})) == [
        "body",
        "invoiceNumber",
        "number",
    ]
    assert (await client.get("/api/received-invoice")).json()["total"] == 0

    # Also when editing
    body = await _create(client)
    path = f"/api/received-invoice/{body['id']}"
    assert await rejected(without_number, "PUT", path) == ["body", "invoiceNumber"]
    assert (await client.get(path)).json()["invoiceNumber"]["formatted"] == "A-0042"


async def test_received_invoices_can_always_be_edited(client: AsyncClient) -> None:
    body = await _create(client, notes="primera versión")
    path = f"/api/received-invoice/{body['id']}"

    other_supplier = {**SUPPLIER, "fullName": "Otra Empresa SL"}
    edited = await client.put(
        path,
        json=_payload(
            issuer=other_supplier,
            invoiceNumber={"number": "7", "suffix": "/B"},
            notes="corregida",
            lines=[{"description": "Alquiler", "quantity": 1, "unitPrice": 600, "taxRate": 21}],
        ),
    )
    assert edited.status_code == 200, edited.text
    edited = edited.json()
    assert (edited["id"], edited["state"]) == (body["id"], "ISSUED")
    assert edited["issuer"]["fullName"] == "Otra Empresa SL"
    assert edited["invoiceNumber"]["formatted"] == "7/B"
    assert [line["description"] for line in edited["lines"]] == ["Alquiler"]
    assert edited["total"] == 726.0

    # ... again and again: there is no point after which it is frozen
    again = await client.put(path, json=_payload(notes="corregida otra vez"))
    assert again.status_code == 200, again.text
    assert (await client.get(path)).json()["notes"] == "corregida otra vez"
    assert (await client.get("/api/received-invoice")).json()["total"] == 1  # not duplicated
    assert (await client.put("/api/received-invoice/999", json=_payload())).status_code == 404


async def test_the_recipient_is_the_fiscal_data_at_the_time_it_was_recorded(
    client: AsyncClient,
) -> None:
    old = await _create(client)

    new_data = {
        "companyName": "Néstor Freelance SL",
        "document": {"type": "CIF", "number": "B12345674"},
        "address": {"street": "Calle Sol 1", "zipCode": "35002", "city": "Las Palmas"},
    }
    assert (await client.put("/api/fiscal-data", json=new_data)).status_code == 200

    # Correcting an invoice recorded earlier does not rewrite who it was addressed to ...
    edited = (await client.put(f"/api/received-invoice/{old['id']}", json=_payload())).json()
    assert edited["recipient"] == old["recipient"]
    # ... while new invoices get the current fiscal data
    assert (await _create(client))["recipient"]["fullName"] == "Néstor Freelance SL"


async def test_received_invoices_need_the_fiscal_data(tenant_client: AsyncClient) -> None:
    response = await tenant_client.post("/api/received-invoice", json=_payload())
    assert response.status_code == 409
    assert "fiscal data" in response.json()["detail"]
    assert (await tenant_client.get("/api/received-invoice")).json()["total"] == 0


async def test_the_supplier_is_validated_like_a_client(client: AsyncClient) -> None:
    async def rejected(**extra) -> list[dict]:
        response = await client.post("/api/received-invoice", json=_payload(**extra))
        assert response.status_code == 422, response.text
        return response.json()["detail"]

    detail = await rejected(issuer=None)
    assert detail[0]["loc"][:2] == ["body", "issuer"]
    detail = await rejected(issuer={**SUPPLIER, "document": {"type": "NIF", "number": "1234"}})
    assert "not a valid NIF" in detail[0]["msg"]
    detail = await rejected(issuer={**SUPPLIER, "fullName": "X"})
    assert detail[0]["loc"] == ["body", "issuer", "fullName"]
    bad_zip = {**SUPPLIER["address"], "zipCode": "ABC"}
    detail = await rejected(issuer={**SUPPLIER, "address": bad_zip})
    assert "postal code" in detail[0]["msg"]
    # Foreign suppliers: any identifier, their own country's rules
    foreign = {
        "fullName": "Software GmbH",
        "document": {"type": "OTHER", "number": "DE123456789"},
        "address": {
            "street": "Hauptstraße 1",
            "zipCode": "10115",
            "city": "Berlin",
            "province": "Berlin",
            "countryIsoCode": "de",
        },
    }
    body = await _create(client, issuer=foreign)
    assert body["issuer"]["address"]["countryIsoCode"] == "DE"


async def test_content_rules_are_the_same_as_for_issued_invoices(client: AsyncClient) -> None:
    async def rejected(**extra) -> str:
        response = await client.post("/api/received-invoice", json=_payload(**extra))
        assert response.status_code == 422, response.text
        return response.json()["detail"][0]["msg"]

    assert "at least 1" in await rejected(lines=[])
    assert "positive amount" in await rejected(lines=[{**LINE, "unitPrice": 0}])
    assert "future" in await rejected(issueDate=(TODAY + timedelta(days=1)).isoformat())
    assert "dueDate" in await rejected(dueDate=(TODAY - timedelta(days=1)).isoformat())


async def test_issued_and_received_invoices_never_mix(client: AsyncClient, serial: Serial) -> None:
    recipient = {
        "fullName": "Tech Solutions SL",
        "document": {"type": "CIF", "number": "B12345674"},
        "address": {
            "street": "Gran Vía 2",
            "zipCode": "48001",
            "city": "Bilbao",
            "province": "Vizcaya",
        },
    }
    client_id = (await client.post("/api/client", json=recipient)).json()["id"]
    issued = await client.post(
        "/api/invoice", json={"clientId": client_id, "lines": [LINE], "state": "DRAFT"}
    )
    assert issued.status_code == 201
    issued = issued.json()
    received = await _create(client)
    assert (issued["kind"], received["kind"]) == ("ISSUED", "RECEIVED")

    # Each collection only lists its own kind, counts included
    for path, own in (("/api/invoice", issued), ("/api/received-invoice", received)):
        collection = (await client.get(path)).json()
        assert (collection["total"], [i["id"] for i in collection["items"]]) == (1, [own["id"]])
    assert (await client.get("/api/invoice", params={"state": "ISSUED"})).json()["total"] == 0

    # ... and the other kind is "not found": it cannot be read or overwritten through the
    # wrong endpoint (which would stamp the wrong parties on it)
    assert (await client.get(f"/api/invoice/{received['id']}")).status_code == 404
    assert (await client.get(f"/api/received-invoice/{issued['id']}")).status_code == 404
    overwrite = await client.put(f"/api/invoice/{received['id']}", json={"lines": [LINE]})
    assert overwrite.status_code == 404
    overwrite = await client.put(f"/api/received-invoice/{issued['id']}", json=_payload())
    assert overwrite.status_code == 404


async def test_received_invoices_do_not_touch_the_serials(
    client: AsyncClient, serial: Serial
) -> None:
    # A supplier that happens to use the same series as ours, with a high number
    await _create(client, invoiceNumber={"prefix": "F-2026-", "number": "99"})
    # Extra fields such as a serial are ignored: received invoices never take one
    body = await _create(client, serialId=serial.id)
    assert body["serialId"] is None

    listed = (await client.get(f"/api/serial/{serial.id}")).json()
    assert (listed["issuedCount"], listed["nextNumber"], listed["locked"]) == (0, 1, False)
    assert (await client.delete(f"/api/serial/{serial.id}")).status_code == 204


async def test_received_invoices_are_per_tenant(
    client: AsyncClient,
    session: AsyncSession,
    other_tenant: User,
    received_invoice_factory: type[ReceivedInvoiceFactory],
) -> None:
    mine = await _create(client)
    theirs = received_invoice_factory(owner=other_tenant, lines=1)
    await session.flush()

    collection = (await client.get("/api/received-invoice")).json()
    assert [i["id"] for i in collection["items"]] == [mine["id"]]
    assert (await client.get(f"/api/received-invoice/{theirs.id}")).status_code == 404
    assert (
        await client.put(f"/api/received-invoice/{theirs.id}", json=_payload())
    ).status_code == 404


async def test_super_admins_have_no_received_invoices(super_admin_client: AsyncClient) -> None:
    assert (await super_admin_client.get("/api/received-invoice")).status_code == 403
    assert (
        await super_admin_client.post("/api/received-invoice", json=_payload())
    ).status_code == 403


async def test_the_database_refuses_a_received_invoice_with_a_serial(
    session: AsyncSession,
    tenant: User,
    serial: Serial,
    received_invoice_factory: type[ReceivedInvoiceFactory],
) -> None:
    invoice = received_invoice_factory(owner=tenant, lines=1)
    assert invoice.kind is InvoiceKind.RECEIVED
    invoice.serial_id = serial.id
    with pytest.raises(IntegrityError, match="ck_invoice_serial_kind"):
        await session.flush()


async def test_the_database_refuses_a_received_draft(
    session: AsyncSession,
    tenant: User,
    received_invoice_factory: type[ReceivedInvoiceFactory],
) -> None:
    received_invoice_factory(owner=tenant, state=InvoiceState.DRAFT, lines=1)
    with pytest.raises(IntegrityError, match="ck_invoice_received_state"):
        await session.flush()

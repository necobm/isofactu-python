"""The client directory (`/api/client`) and how invoices take a copy of a client."""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import ClientFactory, InvoiceFactory
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Serial, Subject
from tests.conftest import login

NESTOR = {
    "fullName": "Néstor Freelance",
    "document": {"type": "NIF", "number": "12345678Z"},
    "address": {
        "street": "Calle Luna 5",
        "zipCode": "35001",
        "city": "Las Palmas",
        "province": "Las Palmas",
    },
}
TECH = {"fullName": "Tech Solutions SL", "document": {"type": "CIF", "number": "B12345678"}}
LINE = {"description": "Consultoría", "quantity": 1, "unitPrice": 100, "taxRate": 21}


async def _create(client: AsyncClient, payload: dict) -> dict:
    response = await client.post("/api/client", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_client_crud(tenant_client: AsyncClient) -> None:
    assert (await tenant_client.get("/api/client")).json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }

    created = await _create(tenant_client, NESTOR)
    assert created["fullName"] == "Néstor Freelance"
    assert created["document"] == {"type": "NIF", "number": "12345678Z"}
    assert created["address"]["countryIsoCode"] == "ES"  # default
    minimal = await _create(tenant_client, {"fullName": "Otro Cliente SL"})
    assert minimal["document"] == {"type": "NIF", "number": ""}

    listed = (await tenant_client.get("/api/client")).json()
    assert listed["total"] == 2
    assert [c["id"] for c in listed["items"]] == [created["id"], minimal["id"]]  # by name
    page = (await tenant_client.get("/api/client", params={"limit": 1, "offset": 1})).json()
    assert (page["total"], [c["id"] for c in page["items"]]) == (2, [minimal["id"]])

    one = await tenant_client.get(f"/api/client/{created['id']}")
    assert one.status_code == 200 and one.json() == created
    assert (await tenant_client.get("/api/client/999")).status_code == 404

    updated = await tenant_client.put(
        f"/api/client/{created['id']}", json={**NESTOR, "fullName": "Néstor Renombrado"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["fullName"] == "Néstor Renombrado"
    assert (await tenant_client.put("/api/client/999", json=NESTOR)).status_code == 404

    for invalid in ({}, {"fullName": "  "}, {**NESTOR, "document": {"type": "DNI"}}):
        response = await tenant_client.post("/api/client", json=invalid)
        assert response.status_code == 422, invalid

    deleted = await tenant_client.delete(f"/api/client/{created['id']}")
    assert deleted.status_code == 204
    assert (await tenant_client.get(f"/api/client/{created['id']}")).status_code == 404
    assert (await tenant_client.delete(f"/api/client/{created['id']}")).status_code == 404
    assert (await tenant_client.get("/api/client")).json()["total"] == 1


async def test_search_clients(tenant_client: AsyncClient) -> None:
    nestor = (await _create(tenant_client, NESTOR))["id"]
    tech = (await _create(tenant_client, TECH))["id"]
    underscore = (await _create(tenant_client, {"fullName": "Sub_Zero SL"}))["id"]

    async def search(q: str) -> tuple[int, list[int]]:
        response = await tenant_client.get("/api/client", params={"q": q})
        assert response.status_code == 200, response.text
        return response.json()["total"], [c["id"] for c in response.json()["items"]]

    assert await search("tech") == (1, [tech])  # case-insensitive, partial match on the name
    assert await search("  néstor ") == (1, [nestor])
    assert await search("b1234") == (1, [tech])  # or on the document number
    assert await search("Sub_") == (1, [underscore])  # LIKE metacharacters are literal
    assert await search("%") == (0, [])
    assert await search("") == (3, [nestor, underscore, tech])  # blank = no filter, by name
    assert await search("nobody") == (0, [])


async def test_clients_are_per_tenant(
    tenant_client: AsyncClient, client: AsyncClient, other_tenant: User
) -> None:
    mine = await _create(tenant_client, TECH)
    await login(client, other_tenant)
    assert (await client.get("/api/client")).json()["total"] == 0
    assert (await client.get(f"/api/client/{mine['id']}")).status_code == 404
    assert (await client.put(f"/api/client/{mine['id']}", json=TECH)).status_code == 404
    assert (await client.delete(f"/api/client/{mine['id']}")).status_code == 404


async def test_invoices_get_their_own_copy_of_the_client(
    tenant_client: AsyncClient, fiscal_data: FiscalData, serial: Serial, session: AsyncSession
) -> None:
    tech = await _create(tenant_client, TECH)
    payload = {"clientId": tech["id"], "lines": [LINE]}

    draft = (await tenant_client.post("/api/invoice", json=payload)).json()
    issued = (
        await tenant_client.post(
            "/api/invoice", json={**payload, "state": "ISSUED", "serialId": serial.id}
        )
    ).json()
    for invoice in (draft, issued):
        assert invoice["recipient"]["fullName"] == "Tech Solutions SL"
        assert invoice["recipient"]["document"] == {"type": "CIF", "number": "B12345678"}
    # One copy per invoice, never the client row itself
    assert draft["recipient"]["id"] != issued["recipient"]["id"]
    assert await session.scalar(select(func.count()).select_from(Subject)) == 2

    # Editing or deleting the client leaves the invoices untouched...
    renamed = await tenant_client.put(
        f"/api/client/{tech['id']}", json={**TECH, "fullName": "Tech Renamed SL"}
    )
    assert renamed.status_code == 200
    for invoice in (draft, issued):
        fetched = (await tenant_client.get(f"/api/invoice/{invoice['id']}")).json()
        assert fetched["recipient"] == invoice["recipient"]
    # ... until a draft is re-pointed at it, which refreshes its copy in place
    saved = await tenant_client.put(f"/api/invoice/{draft['id']}", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["recipient"]["fullName"] == "Tech Renamed SL"
    assert saved.json()["recipient"]["id"] == draft["recipient"]["id"]
    assert await session.scalar(select(func.count()).select_from(Subject)) == 2

    # Saving a draft without a client keeps its recipient as it is
    kept = await tenant_client.put(f"/api/invoice/{draft['id']}", json={"lines": [LINE]})
    assert kept.status_code == 200, kept.text
    assert kept.json()["recipient"] == saved.json()["recipient"]

    assert (await tenant_client.delete(f"/api/client/{tech['id']}")).status_code == 204
    fetched = (await tenant_client.get(f"/api/invoice/{issued['id']}")).json()
    assert fetched["recipient"]["fullName"] == "Tech Solutions SL"
    # A draft pointing at a deleted client cannot be re-pointed at it, but keeps working
    gone = await tenant_client.put(f"/api/invoice/{draft['id']}", json=payload)
    assert gone.status_code == 422
    assert gone.json()["detail"][0]["loc"] == ["body", "clientId"]
    assert (
        await tenant_client.put(f"/api/invoice/{draft['id']}", json={"lines": [LINE]})
    ).status_code == 200

    # Creating always needs a client
    missing = await tenant_client.post("/api/invoice", json={"lines": [LINE]})
    assert missing.status_code == 422
    assert missing.json()["detail"][0]["loc"] == ["body", "clientId"]


async def test_a_recipient_shared_by_legacy_invoices_is_not_rewritten(
    tenant_client: AsyncClient,
    fiscal_data: FiscalData,
    tenant: User,
    invoice_factory: type[InvoiceFactory],
    client_factory: type[ClientFactory],
    session: AsyncSession,
) -> None:
    """Before the Clients module, invoices could share one subject. Re-pointing such a
    draft must not alter the other invoice's recipient."""
    issued = invoice_factory(owner=tenant, lines=1, state=InvoiceState.ISSUED)
    draft = invoice_factory(
        owner=tenant, lines=1, state=InvoiceState.DRAFT, recipient=issued.recipient
    )
    other = client_factory(owner=tenant, full_name="Another Client SL")
    await session.flush()
    shared_id = issued.recipient_id

    saved = await tenant_client.put(
        f"/api/invoice/{draft.id}", json={"clientId": other.id, "lines": [LINE]}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["recipient"]["fullName"] == "Another Client SL"
    assert saved.json()["recipient"]["id"] != shared_id
    untouched = (await tenant_client.get(f"/api/invoice/{issued.id}")).json()
    assert untouched["recipient"]["id"] == shared_id
    assert untouched["recipient"]["fullName"] == issued.recipient.full_name

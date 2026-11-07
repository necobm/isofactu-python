"""Fiscal data of the account (`/api/fiscal-data`) and how it becomes the issuer of invoices."""

from httpx import AsyncClient

from app.invoicing.models import FiscalData
from tests.conftest import login

FISCAL_DATA = {
    "companyName": "Mi Empresa S.L.",
    "document": {"type": "CIF", "number": "b12345674"},
    "address": {
        "street": "Calle Mayor 1",
        "zipCode": "28001",
        "city": "Madrid",
        "province": "Madrid",
        "countryIsoCode": "es",
    },
}
RECIPIENT = {"fullName": "Tech Solutions SL", "document": {"type": "CIF", "number": "B12345678"}}
LINE = {"description": "Consultoría", "quantity": 1, "unitPrice": 100, "taxRate": 21}


async def _recipient_id(client: AsyncClient) -> int:
    response = await client.post("/api/subject", json=RECIPIENT)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_fiscal_data_is_null_until_set_up(tenant_client: AsyncClient) -> None:
    response = await tenant_client.get("/api/fiscal-data")
    assert response.status_code == 200
    assert response.json() is None


async def test_set_and_update_fiscal_data(tenant_client: AsyncClient) -> None:
    created = await tenant_client.put("/api/fiscal-data", json=FISCAL_DATA)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["companyName"] == "Mi Empresa S.L."
    assert body["document"] == {"type": "CIF", "number": "B12345674"}  # upper-cased
    assert body["address"]["countryIsoCode"] == "ES"
    assert body["address"]["province"] == "Madrid"
    assert (await tenant_client.get("/api/fiscal-data")).json() == body

    # Replacing keeps a single row per account; the province is optional
    updated = await tenant_client.put(
        "/api/fiscal-data",
        json={
            **FISCAL_DATA,
            "companyName": "Mi Empresa Renombrada S.L.",
            "address": {"street": "Gran Vía 2", "zipCode": "48001", "city": "Bilbao"},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["companyName"] == "Mi Empresa Renombrada S.L."
    assert updated.json()["address"] == {
        "street": "Gran Vía 2",
        "zipCode": "48001",
        "city": "Bilbao",
        "province": "",
        "countryIsoCode": "ES",
    }
    assert (await tenant_client.get("/api/fiscal-data")).json() == updated.json()


async def test_fiscal_data_is_validated(tenant_client: AsyncClient) -> None:
    async def rejected(payload: dict) -> list:
        response = await tenant_client.put("/api/fiscal-data", json=payload)
        assert response.status_code == 422, response.text
        return [tuple(error["loc"]) for error in response.json()["detail"]]

    assert ("body", "companyName") in await rejected({**FISCAL_DATA, "companyName": "  "})
    assert ("body", "document", "number") in await rejected(
        {**FISCAL_DATA, "document": {"type": "NIF", "number": ""}}
    )
    assert ("body", "document", "type") in await rejected(
        {**FISCAL_DATA, "document": {"type": "DNI", "number": "1"}}
    )
    for field in ("street", "zipCode", "city"):
        locs = await rejected({**FISCAL_DATA, "address": {**FISCAL_DATA["address"], field: ""}})
        assert ("body", "address", field) in locs
    locs = await rejected(
        {**FISCAL_DATA, "address": {**FISCAL_DATA["address"], "countryIsoCode": "ESP"}}
    )
    assert ("body", "address", "countryIsoCode") in locs
    assert ("body", "document") in await rejected({"companyName": "X", "address": {}})

    assert (await tenant_client.get("/api/fiscal-data")).json() is None  # nothing stored


async def test_fiscal_data_is_per_tenant(
    tenant_client: AsyncClient, client: AsyncClient, other_tenant
) -> None:
    assert (await tenant_client.put("/api/fiscal-data", json=FISCAL_DATA)).status_code == 200
    await login(client, other_tenant)
    assert (await client.get("/api/fiscal-data")).json() is None


async def test_invoices_need_the_fiscal_data(tenant_client: AsyncClient) -> None:
    recipient_id = await _recipient_id(tenant_client)
    response = await tenant_client.post(
        "/api/invoice", json={"recipientId": recipient_id, "lines": [LINE]}
    )
    assert response.status_code == 409, response.text
    assert "fiscal data" in response.json()["detail"]
    assert (await tenant_client.get("/api/invoice")).json()["total"] == 0


async def test_invoices_are_stamped_with_the_fiscal_data(
    tenant_client: AsyncClient, fiscal_data: FiscalData
) -> None:
    recipient_id = await _recipient_id(tenant_client)
    payload = {"recipientId": recipient_id, "lines": [LINE]}

    draft = (await tenant_client.post("/api/invoice", json=payload)).json()
    issued = (
        await tenant_client.post(
            "/api/invoice", json={**payload, "state": "ISSUED", "invoiceNumber": {"serial": "F"}}
        )
    ).json()
    for invoice in (draft, issued):
        assert invoice["issuer"]["fullName"] == "Néstor Freelance"
        assert invoice["issuer"]["document"] == {"type": "NIF", "number": "12345678Z"}
        assert invoice["issuer"]["address"]["city"] == "Las Palmas"

    # The fiscal data changes...
    updated = await tenant_client.put("/api/fiscal-data", json=FISCAL_DATA)
    assert updated.status_code == 200, updated.text

    # ... issued invoices keep the issuer they were issued with
    fetched = (await tenant_client.get(f"/api/invoice/{issued['id']}")).json()
    assert fetched["issuer"] == issued["issuer"]
    # ... stored drafts are untouched too, until they are saved again
    fetched = (await tenant_client.get(f"/api/invoice/{draft['id']}")).json()
    assert fetched["issuer"] == draft["issuer"]
    saved = await tenant_client.put(f"/api/invoice/{draft['id']}", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["issuer"]["fullName"] == "Mi Empresa S.L."
    assert saved.json()["issuer"]["document"] == {"type": "CIF", "number": "B12345674"}
    # ... and new invoices carry the new data
    fresh = (await tenant_client.post("/api/invoice", json=payload)).json()
    assert fresh["issuer"]["fullName"] == "Mi Empresa S.L."


async def test_fiscal_data_is_not_a_client(
    tenant_client: AsyncClient, fiscal_data: FiscalData
) -> None:
    """The issuer lives on the invoice: it never shows up among the subjects (clients)."""
    assert (await tenant_client.get("/api/subject")).json() == []

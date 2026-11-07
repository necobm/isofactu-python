"""Numbering serials (`/api/serial`) and how invoices take their numbers from them."""

from datetime import date, timedelta

from httpx import AsyncClient

from app.invoicing.models import FiscalData
from tests.conftest import login

RECIPIENT = {
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
LINE = {"description": "Consultoría", "quantity": 1, "unitPrice": 100, "taxRate": 21}
TODAY = date.today()


async def _create(client: AsyncClient, **payload) -> dict:
    response = await client.post("/api/serial", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _client_id(client: AsyncClient) -> int:
    response = await client.post("/api/client", json=RECIPIENT)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _issue(client: AsyncClient, client_id: int, serial_id: int, **extra) -> dict:
    payload = {
        "clientId": client_id,
        "state": "ISSUED",
        "serialId": serial_id,
        "lines": [LINE],
    }
    response = await client.post("/api/invoice", json={**payload, **extra})
    assert response.status_code == 201, response.text
    return response.json()


async def test_serial_crud(tenant_client: AsyncClient) -> None:
    assert (await tenant_client.get("/api/serial")).json() == []

    created = await _create(tenant_client, prefix="F-2026-")
    assert created == {
        "id": created["id"],
        "prefix": "F-2026-",
        "suffix": "",
        "initialNumber": 1,
        "startDate": None,
        "endDate": None,
        "issuedCount": 0,
        "nextNumber": 1,
        "nextNumberFormatted": "F-2026-1",
        "locked": False,
    }
    other = await _create(
        tenant_client,
        prefix="2026/",
        suffix="-R",
        initialNumber=500,
        startDate="2026-01-01",
        endDate="2026-12-31",
    )
    assert (other["nextNumberFormatted"], other["startDate"]) == ("2026/500-R", "2026-01-01")

    listed = await tenant_client.get("/api/serial")
    assert [s["id"] for s in listed.json()] == [other["id"], created["id"]]  # by prefix
    assert (await tenant_client.get(f"/api/serial/{created['id']}")).json() == created
    assert (await tenant_client.get("/api/serial/999")).status_code == 404

    updated = await tenant_client.put(
        f"/api/serial/{created['id']}",
        json={"prefix": "FAC-", "suffix": "/26", "initialNumber": 10, "endDate": "2026-12-31"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["nextNumberFormatted"], updated.json()["endDate"]) == (
        "FAC-10/26",
        "2026-12-31",
    )
    assert (await tenant_client.put("/api/serial/999", json={"prefix": "X"})).status_code == 404

    deleted = await tenant_client.delete(f"/api/serial/{created['id']}")
    assert deleted.status_code == 204
    assert [s["id"] for s in (await tenant_client.get("/api/serial")).json()] == [other["id"]]
    assert (await tenant_client.delete(f"/api/serial/{created['id']}")).status_code == 404


async def test_serial_validation(tenant_client: AsyncClient) -> None:
    async def rejected(payload: dict) -> str:
        response = await tenant_client.post("/api/serial", json=payload)
        assert response.status_code == 422, response.text
        return " ".join(error["msg"] for error in response.json()["detail"])

    assert "prefix or a suffix" in await rejected({})
    assert "prefix or a suffix" in await rejected({"prefix": "", "suffix": ""})
    assert "endDate" in await rejected(
        {"prefix": "F-", "startDate": "2026-06-01", "endDate": "2026-05-31"}
    )
    assert "greater than or equal to 1" in await rejected({"prefix": "F-", "initialNumber": 0})
    assert "pattern" in await rejected({"prefix": "F 2026"})  # no blanks
    assert "pattern" in await rejected({"suffix": "#"})
    assert (await tenant_client.get("/api/serial")).json() == []

    # Same prefix + suffix twice would produce duplicate numbers
    await _create(tenant_client, prefix="F-", suffix="/A")
    duplicate = await tenant_client.post("/api/serial", json={"prefix": "F-", "suffix": "/A"})
    assert duplicate.status_code == 409
    assert (await tenant_client.post("/api/serial", json={"prefix": "F-"})).status_code == 201
    # ... also when renaming one onto another
    second = (await tenant_client.get("/api/serial")).json()[0]
    clash = await tenant_client.put(
        f"/api/serial/{second['id']}", json={"prefix": "F-", "suffix": "/A"}
    )
    assert clash.status_code == 409


async def test_serials_are_per_tenant(
    tenant_client: AsyncClient, client: AsyncClient, other_tenant
) -> None:
    mine = await _create(tenant_client, prefix="F-")
    await login(client, other_tenant)
    assert (await client.get("/api/serial")).json() == []
    assert (await client.get(f"/api/serial/{mine['id']}")).status_code == 404
    assert (await client.delete(f"/api/serial/{mine['id']}")).status_code == 404
    # The same prefix is fine for another tenant
    assert (await client.post("/api/serial", json={"prefix": "F-"})).status_code == 201


async def test_serials_in_use_are_locked(
    tenant_client: AsyncClient, fiscal_data: FiscalData
) -> None:
    client_id = await _client_id(tenant_client)
    serial = await _create(tenant_client, prefix="F-", initialNumber=5)

    # A draft remembering the serial does not lock it
    draft = await tenant_client.post(
        "/api/invoice",
        json={"clientId": client_id, "serialId": serial["id"], "lines": [LINE]},
    )
    assert draft.status_code == 201 and draft.json()["serialId"] == serial["id"]
    assert (await tenant_client.get(f"/api/serial/{serial['id']}")).json()["locked"] is False

    first = await _issue(tenant_client, client_id, serial["id"])
    assert first["invoiceNumber"]["formatted"] == "F-5"
    fetched = (await tenant_client.get(f"/api/serial/{serial['id']}")).json()
    assert (fetched["locked"], fetched["issuedCount"], fetched["nextNumber"]) == (True, 1, 6)

    base = {"prefix": "F-", "suffix": "", "initialNumber": 5}
    for change in ({"prefix": "G-"}, {"suffix": "/X"}, {"initialNumber": 1}):
        response = await tenant_client.put(f"/api/serial/{serial['id']}", json={**base, **change})
        assert response.status_code == 409, change
    # The dates can still be edited, which is how a serial is retired
    closed = await tenant_client.put(
        f"/api/serial/{serial['id']}", json={**base, "endDate": TODAY.isoformat()}
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["endDate"] == TODAY.isoformat()

    deleted = await tenant_client.delete(f"/api/serial/{serial['id']}")
    assert deleted.status_code == 409
    assert "end date" in deleted.json()["detail"]

    # The issued invoice keeps its number whatever happens to the serial afterwards
    invoice = (await tenant_client.get(f"/api/invoice/{first['id']}")).json()
    assert invoice["invoiceNumber"]["formatted"] == "F-5"


async def test_deleting_an_unused_serial_unlinks_drafts(
    tenant_client: AsyncClient, fiscal_data: FiscalData
) -> None:
    client_id = await _client_id(tenant_client)
    serial = await _create(tenant_client, prefix="TMP-")
    draft = (
        await tenant_client.post(
            "/api/invoice",
            json={"clientId": client_id, "serialId": serial["id"], "lines": [LINE]},
        )
    ).json()
    assert draft["serialId"] == serial["id"]

    assert (await tenant_client.delete(f"/api/serial/{serial['id']}")).status_code == 204
    fetched = (await tenant_client.get(f"/api/invoice/{draft['id']}")).json()
    assert (fetched["state"], fetched["serialId"], fetched["invoiceNumber"]) == (
        "DRAFT",
        None,
        None,
    )


async def test_serial_availability_follows_the_issue_date(
    tenant_client: AsyncClient, fiscal_data: FiscalData
) -> None:
    client_id = await _client_id(tenant_client)
    last_month = TODAY - timedelta(days=30)
    yesterday = TODAY - timedelta(days=1)
    serial = await _create(
        tenant_client,
        prefix="Q-",
        startDate=last_month.isoformat(),
        endDate=yesterday.isoformat(),
    )

    async def attempt(issue_date: date) -> int:
        payload = {
            "clientId": client_id,
            "state": "ISSUED",
            "serialId": serial["id"],
            "issueDate": issue_date.isoformat(),
            "lines": [LINE],
        }
        response = await tenant_client.post("/api/invoice", json=payload)
        if response.status_code == 422:
            assert response.json()["detail"][0]["loc"] == ["body", "serialId"]
            assert "not available" in response.json()["detail"][0]["msg"]
        return response.status_code

    assert await attempt(last_month - timedelta(days=1)) == 422  # before the start
    assert await attempt(last_month) == 201  # bounds are inclusive
    assert await attempt(yesterday) == 201
    assert await attempt(TODAY) == 422  # the end date has passed

    # A draft can still point at it; only issuing is refused
    draft = await tenant_client.post(
        "/api/invoice",
        json={"clientId": client_id, "serialId": serial["id"], "lines": [LINE]},
    )
    assert draft.status_code == 201, draft.text
    issued = await tenant_client.put(
        f"/api/invoice/{draft.json()['id']}",
        json={
            "clientId": client_id,
            "state": "ISSUED",
            "serialId": serial["id"],
            "lines": [LINE],
        },
    )
    assert issued.status_code == 422

    # Open-ended serials are always available
    open_ended = await _create(tenant_client, prefix="O-", startDate=last_month.isoformat())
    far_past = {
        "serialId": open_ended["id"],
        "issueDate": (last_month - timedelta(days=1)).isoformat(),
    }
    before = await tenant_client.post(
        "/api/invoice",
        json={"clientId": client_id, "state": "ISSUED", "lines": [LINE], **far_past},
    )
    assert before.status_code == 422
    assert (await _issue(tenant_client, client_id, open_ended["id"]))["invoiceNumber"][
        "formatted"
    ] == "O-1"

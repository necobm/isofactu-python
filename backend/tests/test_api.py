"""Integration tests for the HTTP API (real PostgreSQL test database)."""

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.fixtures import InvoiceFactory
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import Subject
from app.invoicing.value_objects import InvoiceNumber

ISSUER = {
    "fullName": "Néstor Freelance",
    "document": {"type": "NIF", "number": "12345678Z"},
    "address": {
        "street": "Calle Luna 5",
        "zipCode": "35001",
        "city": "Las Palmas",
        "province": "Las Palmas",
    },
}
RECIPIENT = {"fullName": "Tech Solutions SL", "document": {"type": "CIF", "number": "B12345678"}}
# Minimal valid line: every invoice (draft or issued) needs one with a concept and an amount.
LINE = {"description": "Consultoría", "quantity": 1, "unitPrice": 100, "taxRate": 21}


async def _create_subject(client: AsyncClient, payload: dict) -> int:
    response = await client.post("/api/subject", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_openapi_docs(client: AsyncClient) -> None:
    assert (await client.get("/api/docs")).status_code == 200
    spec = (await client.get("/api/openapi.json")).json()
    assert {"/api/health", "/api/invoice", "/api/invoice/{invoice_id}"} <= set(spec["paths"])


async def test_list_invoices_empty(client: AsyncClient) -> None:
    response = await client.get("/api/invoice")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_create_and_list_invoices(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)

    issue_date = date.today() - timedelta(days=30)
    due_date = issue_date + timedelta(days=30)
    payload = {
        "issueDate": issue_date.isoformat(),
        "state": "ISSUED",
        "invoiceNumber": {"serial": "F-2026", "number": "42"},
        "issuerId": issuer_id,
        "recipientId": recipient_id,
        "notes": "Pago a 30 días.",
        "dueDate": due_date.isoformat(),
        "paymentMethod": "CARD",
        "lines": [
            {"description": "Consultoría", "quantity": 3, "unitPrice": "33.33", "taxRate": 21},
            {"description": "Soporte", "quantity": "1.5", "unitPrice": 100, "taxRate": "10"},
        ],
    }
    created = await client.post("/api/invoice", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["invoiceNumber"] == {"serial": "F-2026", "number": "42", "formatted": "F-2026-42"}
    assert body["state"] == "ISSUED"
    assert (body["notes"], body["dueDate"], body["paymentMethod"]) == (
        "Pago a 30 días.",
        due_date.isoformat(),
        "CARD",
    )
    assert body["issuer"]["document"] == {"type": "NIF", "number": "12345678Z"}
    assert body["issuer"]["address"]["street"] == "Calle Luna 5"
    assert body["recipient"]["address"]["countryIsoCode"] == "ES"
    assert [line["total"] for line in body["lines"]] == [120.99, 165.0]
    assert body["retentionRate"] == 0.0
    assert (body["subtotal"], body["taxAmount"], body["retentionAmount"], body["total"]) == (
        249.99,
        36.0,
        0.0,
        285.99,
    )
    # Amounts are JSON numbers, not strings
    assert all(
        isinstance(line[k], float)
        for line in body["lines"]
        for k in ("quantity", "unitPrice", "taxRate")
    )

    listed = await client.get("/api/invoice")
    assert listed.status_code == 200
    collection = listed.json()
    assert collection["total"] == 1
    assert collection["items"][0]["id"] == body["id"]
    assert collection["items"][0]["lines"][0]["description"] == "Consultoría"

    detail = await client.get(f"/api/invoice/{body['id']}")
    assert detail.status_code == 200
    assert detail.json() == body


async def test_invoices_are_ordered_newest_first_and_paginated(
    client: AsyncClient, invoice_factory: type[InvoiceFactory], subject: Subject
) -> None:
    for issued, number in (
        (date(2026, 1, 10), "1"),
        (date(2026, 3, 1), "2"),
        (date(2026, 2, 15), "3"),
    ):
        invoice_factory(
            issuer=subject,
            recipient=subject,
            issue_date=issued,
            invoice_number=InvoiceNumber(None, number),
            state=InvoiceState.ISSUED,
            lines=1,
        )

    page = (await client.get("/api/invoice", params={"limit": 2})).json()
    assert page["total"] == 3
    assert [i["invoiceNumber"]["formatted"] for i in page["items"]] == ["2", "3"]

    page = (await client.get("/api/invoice", params={"limit": 2, "offset": 2})).json()
    assert [i["invoiceNumber"]["formatted"] for i in page["items"]] == ["1"]


async def test_list_invoices_filtered_by_state(
    client: AsyncClient,
    session: AsyncSession,
    invoice_factory: type[InvoiceFactory],
    subject: Subject,
) -> None:
    states = (
        InvoiceState.ISSUED,
        InvoiceState.DRAFT,
        InvoiceState.ISSUED,
        InvoiceState.DRAFT,
        InvoiceState.DRAFT,
    )
    invoices = [
        invoice_factory(
            issuer=subject, recipient=subject, issue_date=date(2026, 1, day), state=state, lines=1
        )
        for day, state in enumerate(states, start=1)
    ]
    await session.flush()
    first, second, third, fourth, fifth = (invoice.id for invoice in invoices)

    def ids(collection: dict) -> list[int]:
        return [i["id"] for i in collection["items"]]

    everything = (await client.get("/api/invoice")).json()
    assert everything["total"] == 5
    assert ids(everything) == [fifth, fourth, third, second, first]

    drafts = (await client.get("/api/invoice", params={"state": "DRAFT"})).json()
    assert drafts["total"] == 3
    assert ids(drafts) == [fifth, fourth, second]
    assert {i["state"] for i in drafts["items"]} == {"DRAFT"}
    assert {i["invoiceNumber"] for i in drafts["items"]} == {None}  # drafts are numberless

    # `total` reflects the filter, so pagination works per state
    issued = (await client.get("/api/invoice", params={"state": "ISSUED", "limit": 1})).json()
    assert (issued["total"], ids(issued)) == (2, [third])
    assert issued["items"][0]["invoiceNumber"]["formatted"]
    issued = (
        await client.get("/api/invoice", params={"state": "ISSUED", "limit": 1, "offset": 1})
    ).json()
    assert ids(issued) == [first]

    assert (await client.get("/api/invoice", params={"state": "PAID"})).status_code == 422


async def test_create_draft_has_no_number(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    base = {"issuerId": issuer_id, "recipientId": recipient_id, "lines": [LINE]}

    created = await client.post("/api/invoice", json=base)  # state defaults to DRAFT
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["state"], body["invoiceNumber"]) == ("DRAFT", None)
    assert (body["notes"], body["dueDate"], body["paymentMethod"]) == ("", None, "TRANSFER")
    fetched = await client.get(f"/api/invoice/{body['id']}")
    assert fetched.json()["invoiceNumber"] is None

    rejected = await client.post(
        "/api/invoice", json={**base, "state": "DRAFT", "invoiceNumber": {"serial": "F-2026"}}
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["loc"] == ["body", "invoiceNumber"]

    invalid = await client.post("/api/invoice", json={**base, "state": "PAID"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["body", "state"]


async def test_issuing_assigns_the_next_number_of_the_serial(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    base = {"issuerId": issuer_id, "recipientId": recipient_id, "state": "ISSUED", "lines": [LINE]}

    async def issue(invoice_number: dict | None) -> dict:
        payload = {**base, "invoiceNumber": invoice_number} if invoice_number else base
        response = await client.post("/api/invoice", json=payload)
        assert response.status_code == 201, response.text
        return response.json()["invoiceNumber"]

    assert (await issue({"serial": "F-2026"}))["formatted"] == "F-2026-1"
    assert (await issue({"serial": "F-2026"}))["formatted"] == "F-2026-2"
    # An explicit number is respected and the sequence continues after it
    assert (await issue({"serial": "F-2026", "number": "10"}))["formatted"] == "F-2026-10"
    assert (await issue({"serial": "F-2026", "number": ""}))["formatted"] == "F-2026-11"
    # Non-numeric numbers are allowed but do not take part in the sequence
    assert (await issue({"serial": "F-2026", "number": "2026/A"}))["formatted"] == "F-2026-2026/A"
    assert (await issue({"serial": "F-2026"}))["formatted"] == "F-2026-12"
    # Each serial has its own sequence, including the empty one
    assert (await issue({"serial": "PRO-2026"}))["formatted"] == "PRO-2026-1"
    assert (await issue(None)) == {"serial": None, "number": "1", "formatted": "1"}
    assert (await issue({"serial": ""}))["formatted"] == "2"

    serials = (await client.get("/api/invoice", params={"limit": 200})).json()["items"]
    assert all(item["invoiceNumber"] for item in serials)


async def test_retention_is_deducted_from_the_total(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    base = {"issuerId": issuer_id, "recipientId": recipient_id}
    lines = [
        {"description": "Consultoría", "quantity": 1, "unitPrice": "999.99", "taxRate": 21},
        {"description": "Soporte", "quantity": 2, "unitPrice": 50, "taxRate": 10},
    ]

    response = await client.post("/api/invoice", json={**base, "retentionRate": 15, "lines": lines})
    assert response.status_code == 201, response.text
    body = response.json()
    # Lines are not affected: the retention applies to the invoice subtotal as a whole
    assert [(line["taxAmount"], line["total"]) for line in body["lines"]] == [
        (210.0, 1209.99),
        (10.0, 110.0),
    ]
    assert body["retentionRate"] == 15.0
    assert body["retentionAmount"] == 165.0  # 15 % of 1099.99 = 164.9985 -> half-up
    assert (body["subtotal"], body["taxAmount"], body["total"]) == (1099.99, 220.0, 1154.99)

    # Default: no retention
    plain = (await client.post("/api/invoice", json={**base, "lines": lines})).json()
    assert (plain["retentionRate"], plain["retentionAmount"], plain["total"]) == (0.0, 0.0, 1319.99)

    invalid = await client.post("/api/invoice", json={**base, "retentionRate": 101, "lines": lines})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["body", "retentionRate"]


async def test_subjects(client: AsyncClient) -> None:
    subject_id = await _create_subject(client, ISSUER)
    response = await client.get("/api/subject")
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [subject_id]
    assert (await client.get(f"/api/subject/{subject_id}")).json()["fullName"] == "Néstor Freelance"
    assert (await client.get("/api/subject/999")).status_code == 404


async def test_search_subjects(client: AsyncClient) -> None:
    nestor = await _create_subject(client, ISSUER)
    tech = await _create_subject(client, RECIPIENT)
    underscore = await _create_subject(client, {"fullName": "Sub_Zero SL"})

    async def search(q: str) -> list[int]:
        response = await client.get("/api/subject", params={"q": q})
        assert response.status_code == 200, response.text
        return [s["id"] for s in response.json()]

    assert await search("tech") == [tech]  # case-insensitive, partial match on the name
    assert await search("  néstor ") == [nestor]
    assert await search("b1234") == [tech]  # or on the document number
    assert await search("Sub_") == [underscore]  # LIKE metacharacters are literal
    assert await search("%") == []
    assert await search("") == [nestor, underscore, tech]  # blank = no filter, by name
    assert await search("nobody") == []


async def test_invoice_dates_are_validated(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    today = date.today()
    base = {"issuerId": issuer_id, "recipientId": recipient_id, "lines": [LINE]}

    ok = await client.post(
        "/api/invoice",
        json={**base, "issueDate": today.isoformat(), "dueDate": today.isoformat()},
    )
    assert ok.status_code == 201, ok.text

    future = await client.post(
        "/api/invoice", json={**base, "issueDate": (today + timedelta(days=1)).isoformat()}
    )
    assert future.status_code == 422
    assert "issueDate" in future.json()["detail"][0]["msg"]

    early_due = await client.post(
        "/api/invoice",
        json={
            **base,
            "issueDate": today.isoformat(),
            "dueDate": (today - timedelta(days=1)).isoformat(),
        },
    )
    assert early_due.status_code == 422
    assert "dueDate" in early_due.json()["detail"][0]["msg"]


async def test_update_draft_and_issue_it(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    other_id = await _create_subject(client, {"fullName": "Otro Cliente SL"})
    base = {"issuerId": issuer_id, "recipientId": recipient_id, "lines": [LINE]}

    draft = (
        await client.post(
            "/api/invoice",
            json={
                **base,
                "notes": "primera nota",
                "lines": [{"description": "a", "unitPrice": 10}],
            },
        )
    ).json()

    # Editing a draft replaces it wholesale (lines included)
    edited = await client.put(
        f"/api/invoice/{draft['id']}",
        json={
            **base,
            "recipientId": other_id,
            "notes": "nota corregida",
            "retentionRate": 15,
            "lines": [
                {"description": "b", "quantity": 2, "unitPrice": 100, "taxRate": 21},
                {"description": "c", "quantity": 1, "unitPrice": 50, "taxRate": 10},
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["id"] == draft["id"]
    assert (body["state"], body["invoiceNumber"]) == ("DRAFT", None)
    assert body["recipient"]["id"] == other_id
    assert body["notes"] == "nota corregida"
    assert [line["description"] for line in body["lines"]] == ["b", "c"]
    assert (body["subtotal"], body["retentionAmount"], body["total"]) == (250.0, 37.5, 259.5)
    assert (await client.get("/api/invoice")).json()["total"] == 1  # replaced, not duplicated

    # Issuing it from the edit view assigns the next number of the serial. As with any PUT,
    # the payload carries the whole invoice (that is what the edit form sends).
    issued = await client.put(
        f"/api/invoice/{draft['id']}",
        json={
            **base,
            "recipientId": other_id,
            "state": "ISSUED",
            "invoiceNumber": {"serial": "F-2026"},
            "notes": "nota corregida",
            "lines": [{"description": "b", "quantity": 2, "unitPrice": 100, "taxRate": 21}],
        },
    )
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["state"] == "ISSUED"
    assert body["invoiceNumber"]["formatted"] == "F-2026-1"
    assert body["notes"] == "nota corregida"

    # ... and from then on it is immutable
    again = await client.put(f"/api/invoice/{draft['id']}", json={**base, "notes": "x"})
    assert again.status_code == 409, again.text
    assert (await client.get(f"/api/invoice/{draft['id']}")).json()["notes"] == "nota corregida"

    assert (await client.put("/api/invoice/999", json=base)).status_code == 404


async def test_invoice_content_rules_apply_to_drafts_and_issued_alike(client: AsyncClient) -> None:
    issuer_id = await _create_subject(client, ISSUER)
    recipient_id = await _create_subject(client, RECIPIENT)
    base = {"issuerId": issuer_id, "recipientId": recipient_id}

    async def attempt(payload: dict, method: str = "POST", path: str = "/api/invoice"):
        response = await client.request(method, path, json={**base, **payload})
        assert response.status_code == 422, response.text
        return response.json()["detail"]

    for state in ("DRAFT", "ISSUED"):
        # at least one line
        detail = await attempt({"state": state, "lines": []})
        assert detail[0]["loc"] == ["body", "lines"]
        detail = await attempt({"state": state})
        assert detail[0]["loc"] == ["body", "lines"]
        # every line needs a concept (blank counts as missing)
        detail = await attempt({"state": state, "lines": [{**LINE, "description": "   "}]})
        assert detail[0]["loc"] == ["body", "lines", 0, "description"]
        # and the invoice must amount to something
        detail = await attempt({"state": state, "lines": [{**LINE, "unitPrice": 0}]})
        assert "positive amount" in detail[0]["msg"]

    # The same rules guard edits of an existing draft
    draft = (await client.post("/api/invoice", json={**base, "lines": [LINE]})).json()
    detail = await attempt(
        {"lines": [{**LINE, "description": ""}]}, "PUT", f"/api/invoice/{draft['id']}"
    )
    assert detail[0]["loc"] == ["body", "lines", 0, "description"]
    assert (await client.get(f"/api/invoice/{draft['id']}")).json()["lines"][0]["description"] == (
        "Consultoría"
    )

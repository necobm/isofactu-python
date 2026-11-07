"""Reading received invoices from PDF: `POST /api/received-invoice/extract`.

The extractor is replaced by a fake in the API tests (no network); `draft_from` is tested on
its own with raw answers as messy as a model may give; and the LiteLLM extractor is run for
real against a local HTTP server posing as each vendor's API, to check what LiteLLM sends
(PDF, schema, prompt) and how the answer is read back -- no real vendor is contacted.
"""

import base64
import json
import threading
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.fixtures import FiscalDataFactory
from app.invoicing.document_type import DocumentType
from app.invoicing.extraction import (
    INVOICE_SCHEMA,
    SYSTEM_PROMPT,
    ExtractionError,
    LiteLLMInvoiceExtractor,
    UnreadablePdf,
    draft_from,
    get_invoice_extractor,
    pdf_text,
)
from app.invoicing.models import FiscalData
from app.invoicing.value_objects import Address, IdentificationDocument, Issuer

PDF = b"%PDF-1.7\n% a supplier invoice\n%%EOF"

# A raw answer as the model gives it (see `TOOL["input_schema"]`)
RAW: dict[str, Any] = {
    "is_invoice": True,
    "supplier": {
        "name": "Suministros Canarios SL",
        "tax_id": "ESB-12345674",
        "street": "Calle Triana 10",
        "postal_code": "35002",
        "city": "Las Palmas de Gran Canaria",
        "province": "Gran Canaria",
        "country_code": "ES",
    },
    "customer": {"name": "Néstor Freelance", "tax_id": "12345678-Z"},
    "invoice_number": "FV-2026/0042",
    "issue_date": "2026-03-05",
    "due_date": "2026-04-04",
    "lines": [
        {"description": "Tóner", "quantity": 2, "unit_price": 40.5, "vat_rate": 21},
        {"description": "Papel", "amount": "1.234,56", "vat_rate": 21},
    ],
    "irpf_rate": None,
    "payment_method": "TRANSFER",
    "total": 1591.83,
}


class FakeExtractor:
    def __init__(
        self, raw: dict[str, Any] | None = None, error: ExtractionError | None = None
    ) -> None:
        self.raw = RAW if raw is None else raw
        self.error = error
        self.calls: list[tuple[bytes, Issuer | None]] = []

    async def extract(self, pdf: bytes, *, customer: Issuer | None) -> dict[str, Any]:
        self.calls.append((pdf, customer))
        if self.error is not None:
            raise self.error
        return self.raw


@pytest.fixture
def use_extractor(app):
    """Plug an extractor (or None: feature disabled) into the app."""

    def plug(extractor: FakeExtractor | None) -> FakeExtractor | None:
        app.dependency_overrides[get_invoice_extractor] = lambda: extractor
        return extractor

    return plug


async def _upload(client: AsyncClient, content: bytes = PDF, name: str = "factura.pdf"):
    files = {"file": (name, content, "application/pdf")}
    return await client.post("/api/received-invoice/extract", files=files)


# -- the endpoint ---------------------------------------------------------------------------


async def test_extract_prefills_a_received_invoice(
    tenant_client: AsyncClient, fiscal_data: FiscalData, use_extractor
) -> None:
    extractor = use_extractor(FakeExtractor())
    response = await _upload(tenant_client)
    assert response.status_code == 200, response.text
    draft = response.json()

    # The PDF went to the extractor, with the account as the expected customer
    [(pdf, customer)] = extractor.calls
    assert pdf == PDF
    assert customer == fiscal_data.as_issuer()

    assert draft["issuer"] == {
        "fullName": "Suministros Canarios SL",
        "document": {"type": "CIF", "number": "B12345674"},
        "address": {
            "street": "Calle Triana 10",
            "zipCode": "35002",
            "city": "Las Palmas de Gran Canaria",
            "province": "Las Palmas",  # from the postal code
            "countryIsoCode": "ES",
        },
    }
    assert draft["invoiceNumber"] == {"number": "FV-2026/0042"}
    assert (draft["issueDate"], draft["dueDate"]) == ("2026-03-05", "2026-04-04")
    assert (draft["paymentMethod"], draft["retentionRate"]) == ("TRANSFER", 0.0)
    assert draft["lines"] == [
        {"description": "Tóner", "quantity": 2.0, "unitPrice": 40.5, "taxRate": 21.0},
        {"description": "Papel", "quantity": 1.0, "unitPrice": 1234.56, "taxRate": 21.0},
    ]
    assert draft["printedTotal"] == 1591.83
    assert (draft["customerName"], draft["addressedToAccount"]) == ("Néstor Freelance", True)

    # Nothing is stored ...
    assert (await tenant_client.get("/api/received-invoice")).json()["total"] == 0
    # ... and the reviewed draft is a valid received invoice as it is
    payload = {k: v for k, v in draft.items() if k in {"issuer", "invoiceNumber", "lines"}}
    payload |= {"issueDate": draft["issueDate"], "dueDate": draft["dueDate"]}
    saved = await tenant_client.post("/api/received-invoice", json=payload)
    assert saved.status_code == 201, saved.text
    assert saved.json()["total"] == 1591.83  # the lines add up to the printed total


async def test_extract_without_fiscal_data(tenant_client: AsyncClient, use_extractor) -> None:
    extractor = use_extractor(FakeExtractor())
    draft = (await _upload(tenant_client)).json()
    assert extractor.calls[0][1] is None  # no customer hint
    assert draft["addressedToAccount"] is None


async def test_extract_flags_invoices_addressed_to_someone_else(
    tenant_client: AsyncClient, fiscal_data: FiscalData, use_extractor
) -> None:
    use_extractor(FakeExtractor({**RAW, "customer": {"name": "Otra SL", "tax_id": "B87654321"}}))
    draft = (await _upload(tenant_client)).json()
    assert (draft["customerName"], draft["addressedToAccount"]) == ("Otra SL", False)


async def test_extract_when_pdf_import_is_disabled(
    tenant_client: AsyncClient, use_extractor
) -> None:
    use_extractor(None)
    response = await _upload(tenant_client)
    assert response.status_code == 503
    assert "LLM_PROVIDER" in response.json()["detail"]


def test_pdf_import_follows_the_llm_settings(monkeypatch) -> None:
    settings = get_settings()
    for provider, model in (("", ""), ("openai", ""), ("", "gpt-4o"), ("  ", "  ")):
        monkeypatch.setattr(settings, "llm_provider", provider)
        monkeypatch.setattr(settings, "llm_model", model)
        assert (settings.pdf_import_enabled, get_invoice_extractor()) == (False, None)

    # The model is named the LiteLLM way, `provider/model`, whichever way it is written
    monkeypatch.setattr(settings, "llm_provider", "Anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-4-5")
    assert settings.llm_model_id == "anthropic/claude-sonnet-4-5"
    monkeypatch.setattr(settings, "llm_model", "anthropic/claude-sonnet-4-5")
    assert settings.llm_model_id == "anthropic/claude-sonnet-4-5"

    monkeypatch.setattr(settings, "llm_api_key", " sk-test ")
    monkeypatch.setattr(settings, "llm_api_base", "")
    extractor = get_invoice_extractor()
    assert isinstance(extractor, LiteLLMInvoiceExtractor)
    assert (extractor.model, extractor.api_key, extractor.api_base) == (
        "anthropic/claude-sonnet-4-5",
        "sk-test",
        None,  # LiteLLM's default endpoint for the vendor
    )
    assert (extractor.reads_pdf, extractor.structured) == (True, True)


async def test_extract_rejects_what_is_not_a_pdf(
    tenant_client: AsyncClient, use_extractor, monkeypatch
) -> None:
    extractor = use_extractor(FakeExtractor())
    response = await _upload(tenant_client, b"PK\x03\x04 a zip file", "factura.pdf")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]
    assert response.json()["detail"][0]["type"] == "not_pdf"

    monkeypatch.setattr(get_settings(), "invoice_pdf_max_bytes", len(PDF) - 1)
    assert (await _upload(tenant_client)).status_code == 413
    assert (await tenant_client.post("/api/received-invoice/extract")).status_code == 422
    assert extractor.calls == []  # never sent anywhere


async def test_extract_when_the_pdf_cannot_be_read(
    tenant_client: AsyncClient, use_extractor
) -> None:
    use_extractor(FakeExtractor(error=ExtractionError("boom")))
    assert (await _upload(tenant_client)).status_code == 502

    use_extractor(FakeExtractor({"is_invoice": False, "supplier": {}, "lines": []}))
    response = await _upload(tenant_client)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "not_invoice"

    # A scan, with a model that can only read text
    use_extractor(FakeExtractor(error=UnreadablePdf("no_text", "The PDF has no text")))
    response = await _upload(tenant_client)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "no_text"


async def test_extract_needs_a_tenant(
    client: AsyncClient, super_admin_client: AsyncClient, use_extractor
) -> None:
    extractor = use_extractor(FakeExtractor())
    assert (await _upload(client)).status_code == 401
    assert (await _upload(super_admin_client)).status_code == 403
    assert extractor.calls == []


# -- normalising the raw answer -------------------------------------------------------------


def _account(number: str = "12345678Z") -> FiscalData:
    return FiscalDataFactory.build(
        company_name="Néstor Freelance",
        document=IdentificationDocument(DocumentType.NIF, number),
        address=Address("Calle Luna 5", "35001", "Las Palmas", "Las Palmas", "ES"),
    )


def _supplier(**fields: Any):
    return draft_from({"supplier": fields, "lines": []}, None).issuer


def test_supplier_identification_is_classified_by_its_check_character() -> None:
    assert _supplier(tax_id="ESB12345674").document.model_dump() == {
        "type": DocumentType.CIF,
        "number": "B12345674",
    }
    assert _supplier(tax_id="12.345.678-z").document.number == "12345678Z"
    assert _supplier(tax_id="12.345.678-z").document.type is DocumentType.NIF
    assert _supplier(tax_id="X1234567L").document.type is DocumentType.NIF  # NIE
    # A misread check character keeps its type, so that the form flags it for correction
    assert _supplier(tax_id="B12345675").document.type is DocumentType.CIF
    # Foreign VAT numbers
    foreign = _supplier(tax_id="DE 123 456 789", country_code="de", province="Berlin")
    assert (foreign.document.type, foreign.document.number) == (DocumentType.OTHER, "DE123456789")
    assert (foreign.address.country_iso_code, foreign.address.province) == ("DE", "Berlin")
    assert _supplier().document.number == ""


def test_supplier_province_comes_from_the_postal_code() -> None:
    # Names printed in other official languages, or wrong, do not matter for Spain
    assert _supplier(postal_code="48001", province="Bizkaia").address.province == "Vizcaya"
    assert _supplier(postal_code="15001", province="La Coruña").address.province == "A Coruña"
    assert _supplier(postal_code="", province="madrid").address.province == "Madrid"
    assert _supplier(postal_code="", province="Atlantis").address.province == ""
    # Unknown country codes fall back to Spain, the form's default
    assert _supplier(country_code="XX").address.country_iso_code == "ES"


def test_lines_are_normalised() -> None:
    lines = draft_from(
        {
            "lines": [
                {"description": "Horas", "quantity": 3, "amount": 100},  # price from the amount
                {"description": "Descuento", "unit_price": -10.004, "vat_rate": "21"},
                {"description": "Exento", "unit_price": "15,5", "vat_rate": 250},  # bad rate
                {"quantity": 1},  # nothing usable
                "garbage",
                {"description": "  Sin   precio  "},
            ]
        },
        None,
    ).lines
    assert [
        (line.description, line.quantity, line.unit_price, line.tax_rate) for line in lines
    ] == [
        ("Horas", Decimal("3.00"), Decimal("33.33"), Decimal("0.00")),
        ("Descuento", Decimal("1.00"), Decimal("-10.00"), Decimal("21.00")),
        ("Exento", Decimal("1.00"), Decimal("15.50"), Decimal("0.00")),
        ("Sin precio", Decimal("1.00"), Decimal("0.00"), Decimal("0.00")),
    ]


def test_the_rest_of_the_draft_is_normalised() -> None:
    draft = draft_from(
        {
            "invoice_number": "  A-0042 ",
            "issue_date": "05/03/2026",  # not ISO: dropped rather than guessed
            "due_date": "2026-04-04T00:00:00",
            "irpf_rate": -15,
            "payment_method": "BIZUM",
            "total": "abc",
            "customer": {"tax_id": "ES 12345678Z", "name": "Néstor"},
        },
        _account(),
    )
    assert draft.invoice_number is not None and draft.invoice_number.number == "A-0042"
    assert (draft.issue_date, draft.due_date) == (None, date(2026, 4, 4))
    assert (draft.retention_rate, draft.payment_method) == (Decimal("15.00"), None)
    assert (draft.printed_total, draft.addressed_to_account) == (None, True)

    assert draft_from({"customer": {"tax_id": "B12345674"}}, _account()).addressed_to_account is (
        False
    )
    # Whatever the shape of the answer, a (blank) draft comes out
    empty = draft_from({"supplier": "?", "lines": "?", "customer": 3, "invoice_number": 7}, None)
    assert (empty.issuer.full_name, empty.lines, empty.invoice_number.number) == ("", [], "7")


# -- the LiteLLM extractor, against fake vendor APIs ----------------------------------------


def text_pdf(*lines: str) -> bytes:
    """A small, valid PDF with a text layer (no lines: a page without text, like a scan)."""
    stream = (
        b"BT /F1 12 Tf 72 720 Td 14 TL "
        + b" ".join(b"(" + line.encode("latin-1") + b") '" for line in lines)
        + b" ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    pdf, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return pdf


class FakeVendor:
    """A local HTTP server answering like a vendor's API, recording what it receives."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.replies: list[tuple[int, dict[str, Any]]] = []
        vendor = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 -- http.server API
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                vendor.requests.append((self.path, dict(self.headers), body))
                status, reply = vendor.replies.pop(0)
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def reply(self, body: dict[str, Any], status: int = 200) -> None:
        self.replies.append((status, body))


@pytest.fixture
def vendor() -> Iterator[FakeVendor]:
    fake = FakeVendor()
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def _extractor(model: str, vendor: FakeVendor) -> LiteLLMInvoiceExtractor:
    return LiteLLMInvoiceExtractor(
        model, api_key="sk-test", api_base=vendor.url, timeout=10, retries=0
    )


def _anthropic_reply(text: str) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def _openai_reply(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


CUSTOMER = Issuer(full_name="Néstor Freelance", document_number="12345678Z")


async def test_anthropic_gets_the_pdf_and_the_schema(vendor: FakeVendor) -> None:
    vendor.reply(_anthropic_reply(json.dumps(RAW)))
    extractor = _extractor("anthropic/claude-sonnet-4-5", vendor)
    assert await extractor.extract(PDF, customer=CUSTOMER) == RAW

    [(path, headers, body)] = vendor.requests
    assert path == "/v1/messages"
    assert headers["x-api-key"] == "sk-test"
    assert body["model"] == "claude-sonnet-4-5"
    assert body["system"][0]["text"] == SYSTEM_PROMPT
    # The PDF goes as an Anthropic document, the schema as its structured output format
    document, instructions = body["messages"][0]["content"]
    assert document["type"] == "document"
    assert document["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(document["source"]["data"]) == PDF
    assert "Néstor Freelance" in instructions["text"] and "12345678Z" in instructions["text"]
    assert body["output_format"]["schema"] == INVOICE_SCHEMA


async def test_openai_gets_the_pdf_and_the_schema(vendor: FakeVendor) -> None:
    # Answers wrapped in a code fence are read too
    vendor.reply(_openai_reply(f"```json\n{json.dumps(RAW)}\n```"))
    extractor = _extractor("openai/gpt-4o", vendor)
    assert await extractor.extract(PDF, customer=None) == RAW

    [(path, headers, body)] = vendor.requests
    assert path == "/chat/completions"
    assert headers["authorization"] == "Bearer sk-test"
    assert body["model"] == "gpt-4o"
    file_part, instructions = body["messages"][1]["content"]
    assert file_part["type"] == "file"
    prefix, data = file_part["file"]["file_data"].split(",", 1)
    assert (prefix, base64.b64decode(data)) == ("data:application/pdf;base64", PDF)
    assert body["response_format"]["json_schema"]["schema"] == INVOICE_SCHEMA
    assert "addressed to" not in instructions["text"]  # no fiscal data, no customer hint


async def test_models_that_cannot_read_pdfs_get_its_text(vendor: FakeVendor) -> None:
    vendor.reply(_openai_reply(json.dumps(RAW)))
    # Unknown to LiteLLM: assumed to read neither PDF files nor structured output
    extractor = _extractor("openai/some-local-model", vendor)
    assert (extractor.reads_pdf, extractor.structured) == (False, False)
    pdf = text_pdf("FACTURA FV-2026/0042", "Suministros Canarios SL - B12345674", "Total 1591,83")
    assert await extractor.extract(pdf, customer=CUSTOMER) == RAW

    [(_, _, body)] = vendor.requests
    text_part, instructions = body["messages"][1]["content"]
    assert text_part["type"] == "text"
    assert "FACTURA FV-2026/0042" in text_part["text"] and "Total 1591,83" in text_part["text"]
    assert "response_format" not in body
    assert json.dumps(INVOICE_SCHEMA, ensure_ascii=False) in instructions["text"]


async def test_scans_need_a_model_that_reads_pdfs(vendor: FakeVendor) -> None:
    extractor = _extractor("openai/some-local-model", vendor)
    with pytest.raises(UnreadablePdf) as error:
        await extractor.extract(text_pdf(), customer=None)
    assert error.value.reason == "no_text"
    with pytest.raises(UnreadablePdf) as error:
        await extractor.extract(b"%PDF-1.4 broken beyond repair", customer=None)
    assert error.value.reason == "not_pdf"
    assert vendor.requests == []  # nothing was sent


def test_pdf_text_reads_the_text_layer() -> None:
    assert pdf_text(text_pdf("Hola", "Adiós")).splitlines() == ["Hola", "Adiós"]


async def test_vendor_failures(vendor: FakeVendor) -> None:
    extractor = _extractor("openai/gpt-4o", vendor)

    vendor.reply({"error": {"message": "overloaded", "type": "server_error"}}, status=500)
    with pytest.raises(ExtractionError):
        await extractor.extract(PDF, customer=None)

    vendor.reply(_openai_reply("Sorry, I cannot read this document."))
    with pytest.raises(ExtractionError, match="JSON"):
        await extractor.extract(PDF, customer=None)

    vendor.reply(_openai_reply("[1, 2, 3]"))
    with pytest.raises(ExtractionError):
        await extractor.extract(PDF, customer=None)

    unreachable = LiteLLMInvoiceExtractor(
        "openai/gpt-4o", api_key="sk-test", api_base="http://127.0.0.1:9", timeout=5, retries=0
    )
    with pytest.raises(ExtractionError):
        await unreachable.extract(PDF, customer=None)

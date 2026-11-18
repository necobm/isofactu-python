"""PDF export of issued invoices (`GET /api/invoice/{id}/pdf`)."""

import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.fixtures import InvoiceFactory, ReceivedInvoiceFactory
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.models import FiscalData, Serial
from app.invoicing.pdf import format_amount, format_rate, pdf_filename
from app.invoicing.schemas import InvoiceNumberSchema, InvoiceRead

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
ISSUE_DATE = date.today() - timedelta(days=10)
DUE_DATE = ISSUE_DATE + timedelta(days=30)


@pytest.fixture
def client(tenant_client: AsyncClient, fiscal_data: FiscalData, serial: Serial) -> AsyncClient:
    """A tenant with fiscal data ("Jesús Freelance") and a `F-2026-` serial."""
    return tenant_client


async def _issue(client: AsyncClient, **overrides) -> dict:
    created = await client.post("/api/client", json=CLIENT)
    assert created.status_code == 201, created.text
    serials = (await client.get("/api/serial")).json()
    payload = {
        "issueDate": ISSUE_DATE.isoformat(),
        "dueDate": DUE_DATE.isoformat(),
        "state": "ISSUED",
        "serialId": serials[0]["id"],
        "clientId": created.json()["id"],
        "paymentMethod": "TRANSFER",
        "retentionRate": 15,
        "notes": "Pago a 30 días.\nIBAN ES91 2100 0418 4502 0005 1332",
        "lines": [
            {"description": "Consultoría", "quantity": 3, "unitPrice": "33.33", "taxRate": 21},
            {"description": "Soporte <b>& mantenimiento</b>", "quantity": "1.5",
             "unitPrice": 10000, "taxRate": 10},
        ],
        **overrides,
    }  # fmt: skip
    response = await client.post("/api/invoice", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _raw_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def _text(pdf: bytes) -> str:
    """The text of the PDF with its whitespace collapsed (table cells come out one per
    line), so that a table row reads as a single line."""
    return " ".join(_raw_text(pdf).split())


def _sized_text(pdf: bytes) -> list[tuple[float, str]]:
    """Every piece of text of the first page with the size it is drawn at."""
    found: list[tuple[float, str]] = []

    def visit(text, _cm, tm, _font, size):
        if text.strip():
            found.append((round(size * tm[3], 2), text.strip()))

    PdfReader(io.BytesIO(pdf)).pages[0].extract_text(visitor_text=visit)
    return found


async def test_issued_invoice_as_pdf(client: AsyncClient) -> None:
    invoice = await _issue(client)

    response = await client.get(f"/api/invoice/{invoice['id']}/pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="Factura-F-2026-1.pdf"'
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(response.content))
    assert reader.metadata.title == "Factura F-2026-1"
    assert reader.metadata.author == "Jesús Freelance"

    text = _text(response.content)
    expected = [
        # issuer: company name and fiscal data
        "Jesús Freelance",
        "NIF: 12345678Z",
        "Calle Luna 5",
        "35001 Las Palmas",
        "Las Palmas, España",
        # number, dates, payment method
        "F-2026-1",
        f"Fecha de emisión {ISSUE_DATE:%d/%m/%Y}",
        f"Fecha de vencimiento {DUE_DATE:%d/%m/%Y}",
        "Forma de pago Transferencia bancaria",
        # client
        "Tech Solutions SL",
        "CIF: B12345674",
        "Gran Vía 2",
        "48001 Bilbao",
        "Vizcaya, España",
        # lines: concept, quantity, unit price, VAT rate, base, VAT, total
        "Consultoría 3,00 33,33 € 21 % 99,99 € 21,00 € 120,99 €",
        "Soporte <b>& mantenimiento</b> 1,50 10.000,00 € 10 % 15.000,00 € 1500,00 € 16.500,00 €",
        # totals
        "Base imponible 15.099,99 €",
        "IVA 1521,00 €",
        "Retención IRPF (15 %) -2265,00 €",
        "TOTAL 14.355,99 €",
        # notes
        "NOTAS Pago a 30 días. IBAN ES91 2100 0418 4502 0005 1332",
        # footer
        "Página 1 de 1",
    ]
    for snippet in expected:
        assert snippet in text, snippet
    # The line breaks of the notes are kept
    assert "Pago a 30 días.\nIBAN ES91" in _raw_text(response.content)
    assert (invoice["subtotal"], invoice["total"]) == (15099.99, 14355.99)


async def test_the_invoice_number_is_the_largest_text(client: AsyncClient) -> None:
    invoice = await _issue(client)

    pdf = (await client.get(f"/api/invoice/{invoice['id']}/pdf")).content

    sizes = _sized_text(pdf)
    largest_size, largest_text = max(sizes)
    assert largest_text == "F-2026-1"
    company_size = max(size for size, text in sizes if text == "Jesús Freelance")
    body_size = max(size for size, text in sizes if text.startswith("Gran Vía 2"))
    assert largest_size > company_size > body_size
    # Nothing else shares the size of the number
    assert [text for size, text in sizes if size == largest_size] == ["F-2026-1"]


async def test_without_retention_nor_due_date(client: AsyncClient) -> None:
    invoice = await _issue(client, retentionRate=0, dueDate=None, notes="", paymentMethod="CARD")

    text = _text((await client.get(f"/api/invoice/{invoice['id']}/pdf")).content)

    assert "Retención" not in text
    assert "Fecha de vencimiento" not in text
    assert "NOTAS" not in text
    assert "Forma de pago Tarjeta" in text
    assert "TOTAL 16.620,99 €" in text


async def test_the_pdf_keeps_the_data_the_invoice_was_issued_with(client: AsyncClient) -> None:
    invoice = await _issue(client)
    # Later changes to the fiscal data (or the client) do not alter an issued invoice
    renamed = {
        "companyName": "Otra Empresa SL",
        "document": {"type": "CIF", "number": "B12345674"},
        "address": CLIENT["address"],
    }
    assert (await client.put("/api/fiscal-data", json=renamed)).status_code == 200

    text = _text((await client.get(f"/api/invoice/{invoice['id']}/pdf")).content)

    assert "Jesús Freelance" in text
    assert "Otra Empresa SL" not in text


async def test_long_invoices_span_several_pages(client: AsyncClient) -> None:
    lines = [
        {"description": f"Concepto número {n}", "quantity": 1, "unitPrice": 10, "taxRate": 21}
        for n in range(1, 81)
    ]
    invoice = await _issue(client, lines=lines)

    pdf = (await client.get(f"/api/invoice/{invoice['id']}/pdf")).content

    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) > 1
    for number, page in enumerate(pages, start=1):
        text = " ".join(page.extract_text().split())
        assert f"Página {number} de {len(pages)}" in text
        assert "Factura F-2026-1 · Jesús Freelance" in text
        assert "Concepto Cant. Precio unit." in text  # the table header is repeated
    last_page = " ".join(pages[-1].extract_text().split())
    assert "Concepto número 80" in last_page
    assert "TOTAL 848,00 €" in last_page  # 80 × 12,10 € − 15 % IRPF of 800 €


async def test_drafts_cannot_be_exported(client: AsyncClient) -> None:
    draft = await _issue(client, state="DRAFT")

    response = await client.get(f"/api/invoice/{draft['id']}/pdf")

    assert response.status_code == 409
    assert response.json()["detail"] == "Only issued invoices can be exported as PDF"


async def test_only_the_tenants_own_issued_invoices(
    client: AsyncClient, session: AsyncSession, tenant: User, other_tenant: User
) -> None:
    theirs = InvoiceFactory(owner=other_tenant, state=InvoiceState.ISSUED)
    expense = ReceivedInvoiceFactory(owner=tenant)
    await session.flush()

    assert (await client.get(f"/api/invoice/{theirs.id}/pdf")).status_code == 404
    assert (await client.get(f"/api/invoice/{expense.id}/pdf")).status_code == 404
    assert (await client.get("/api/invoice/999999/pdf")).status_code == 404


async def test_requires_a_tenant_session(
    app, client: AsyncClient, super_admin_client: AsyncClient
) -> None:
    invoice = await _issue(client)
    path = f"/api/invoice/{invoice['id']}/pdf"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get(path)).status_code == 401
    assert (await super_admin_client.get(path)).status_code == 403


async def test_generated_invoices_render(
    client: AsyncClient, session: AsyncSession, tenant: User, fiscal_data: FiscalData
) -> None:
    """Whatever the factories produce (any payment method, retention, foreign country...)."""
    invoices = InvoiceFactory.create_batch(
        5, owner=tenant, issuer=fiscal_data.as_issuer(), state=InvoiceState.ISSUED
    )
    await session.flush()

    for invoice in invoices:
        response = await client.get(f"/api/invoice/{invoice.id}/pdf")
        assert response.status_code == 200, response.text
        text = _text(response.content)
        assert str(invoice.invoice_number) in text
        assert invoice.recipient.full_name in text


# -- formatting -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "0,00"),
        ("5", "5,00"),
        ("1234.5", "1234,50"),  # like Intl.NumberFormat('es-ES'): 4 digits are not grouped
        ("12345.678", "12.345,68"),
        ("1234567.891", "1.234.567,89"),
        ("-2265", "-2265,00"),
        ("-12345.5", "-12.345,50"),
        ("0.005", "0,01"),  # half-up, as everywhere else
    ],
)
def test_format_amount(value: str, expected: str) -> None:
    assert format_amount(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("21.00", "21 %"), ("10.50", "10,5 %"), ("0.00", "0 %"), ("100.00", "100 %"), ("7", "7 %")],
)
def test_format_rate(value: str, expected: str) -> None:
    assert format_rate(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("prefix", "number", "suffix", "expected"),
    [
        ("F-2026-", "42", "", "Factura-F-2026-42.pdf"),
        ("", "42", "/A", "Factura-42-A.pdf"),
        ("FV 2026/", "7", "", "Factura-FV-2026-7.pdf"),
        ("../", "1", "", "Factura-1.pdf"),
    ],
)
def test_pdf_filename(prefix: str, number: str, suffix: str, expected: str) -> None:
    number_schema = InvoiceNumberSchema(prefix=prefix, number=number, suffix=suffix)
    invoice = InvoiceRead.model_construct(id=9, invoice_number=number_schema)
    assert pdf_filename(invoice) == expected

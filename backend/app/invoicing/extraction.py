"""Reading received invoices from PDF, to pre-fill the received invoice form.

Supplier invoices come in any layout (and are sometimes scans), so instead of parsing their
text with rules the PDF is handed to an LLM, which answers with the data we need as JSON
following ``INVOICE_SCHEMA``. Each tenant chooses the vendor, model and API key in its
settings (AI module: Gemini, Anthropic, OpenAI, Azure OpenAI, Amazon Bedrock), and the call
goes through LiteLLM. Nothing is stored: the result is a *draft* the user reviews in the form
before saving.

Two stages, kept apart on purpose:

1. An ``InvoiceExtractor`` returns the raw answer (a dict following ``INVOICE_SCHEMA``).
   ``LiteLLMInvoiceExtractor`` is the real one; tests plug in fakes.
2. ``draft_from`` turns that raw answer into a ``ReceivedInvoiceDraft``. The answer is
   treated as untrusted input: every value is type-checked, bounded and normalised (the
   NIF / CIF type is decided by its check character, the province by the postal code,
   amounts are rounded to cents), and whatever cannot be used is left empty for the user.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any, Protocol

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.deps import CurrentTenant
from app.ai.providers import import_litellm
from app.ai.repository import AiSettingsRepository
from app.ai.service import connection_for
from app.core.config import get_settings
from app.core.crypto import SecretDecryptionError, get_secret_box
from app.core.database import get_session
from app.geo import service as geo
from app.invoicing import spanish_ids
from app.invoicing.document_type import DocumentType
from app.invoicing.models import FiscalData
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.schemas import (
    AddressSchema,
    IdentificationDocumentSchema,
    InvoiceLineBase,
    PartyDraft,
    ReceivedInvoiceDraft,
    ReceivedInvoiceNumberWrite,
)
from app.invoicing.value_objects import Issuer

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("99999999.99")  # what Numeric(10, 2) can hold
MAX_LINES = 200
# Models that cannot read PDF files get the text of the invoice instead, within limits
MAX_TEXT_PAGES = 10
MAX_TEXT_CHARS = 40_000


class ExtractionError(Exception):
    """The PDF could not be read (service unavailable, refused, or no usable answer)."""


class UnreadablePdf(ExtractionError):
    """The PDF itself is the problem: it cannot be opened, or it has no text for a model
    that cannot read PDF files (a scan). ``reason`` is ``not_pdf`` or ``no_text``."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class InvoiceExtractor(Protocol):
    async def extract(self, pdf: bytes, *, customer: Issuer | None) -> dict[str, Any]:
        """The data read from the invoice, following ``INVOICE_SCHEMA``. ``customer`` is
        who the invoice should be addressed to (the account), which helps telling the
        supplier apart. Raises ``ExtractionError``."""
        ...


# -- the question asked to the model -------------------------------------------------------
# A deliberately plain JSON schema (no type unions, no nulls, every field optional) so that
# every vendor's structured-output dialect accepts it; missing data is simply left out.


def _field(type_: str, description: str, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "description": description, **extra}


def _object(description: str, properties: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": properties,
        "additionalProperties": False,
        **extra,
    }


def _party(description: str) -> dict[str, Any]:
    return _object(
        description,
        {
            "name": _field("string", "Legal or trade name, as printed"),
            "tax_id": _field(
                "string",
                "Tax identification number exactly as printed: NIF, CIF, NIE, or a foreign "
                "VAT number",
            ),
            "street": _field("string", "Street address (street, number, floor...)"),
            "postal_code": _field("string", "Postal code"),
            "city": _field("string", "City or town"),
            "province": _field("string", "Province, state or region"),
            "country_code": _field(
                "string", "ISO 3166-1 alpha-2 code of the address country, e.g. ES"
            ),
        },
    )


SCHEMA_NAME = "supplier_invoice"
INVOICE_SCHEMA: dict[str, Any] = _object(
    "The data of an invoice received from a supplier",
    {
        "is_invoice": _field(
            "boolean",
            "false when the document is not an invoice (a quote, a delivery note, a bank "
            "statement, something unrelated...)",
        ),
        "supplier": _party(
            "The party that ISSUED the invoice: the seller / provider. Never the customer."
        ),
        "customer": _party("The party the invoice is addressed to (the buyer)."),
        "invoice_number": _field(
            "string",
            "The complete invoice number as printed, including any series, prefix or suffix, "
            "e.g. 'FV-2026/0042'",
        ),
        "issue_date": _field("string", "Invoice date, as YYYY-MM-DD"),
        "due_date": _field("string", "Payment due date, as YYYY-MM-DD"),
        "lines": {
            "type": "array",
            "description": "The concepts invoiced, in order",
            "items": _object(
                "A concept of the invoice",
                {
                    "description": _field("string", "What is invoiced"),
                    "quantity": _field("number", "Units; 1 when not shown"),
                    "unit_price": _field(
                        "number",
                        "Price per unit BEFORE VAT, in the invoice currency, with any line "
                        "discount already applied",
                    ),
                    "vat_rate": _field(
                        "number",
                        "VAT (IVA) or IGIC percentage applied to the line, e.g. 21; 0 when exempt",
                    ),
                    "amount": _field("number", "Line amount before VAT, as printed"),
                },
                required=["description"],
            ),
        },
        "irpf_rate": _field(
            "number",
            "IRPF withholding percentage deducted from the total (e.g. 15 or 19), as a "
            "positive number; leave it out when there is none",
        ),
        "payment_method": _field(
            "string",
            "How the invoice is to be paid",
            enum=[method.value for method in PaymentMethod],
        ),
        "total": _field(
            "number",
            "The final amount to pay, as printed: base + VAT, minus any IRPF withheld",
        ),
    },
    required=["is_invoice", "supplier", "lines"],
)

SYSTEM_PROMPT = "\n".join(
    [
        "You read invoices that a Spanish freelancer or small business received from its "
        "suppliers and answer with their data as JSON. Rules:",
        "- Copy names, numbers and identifiers exactly as printed; do not invent anything. "
        "Leave out whatever does not appear in the document.",
        "- The supplier is the party that issued the invoice; the customer is the party it is "
        "addressed to. Do not mix them up.",
        "- Dates are written day first in Spain (05/03/2026 is 5 March 2026): output YYYY-MM-DD.",
        "- Amounts are plain numbers in the invoice currency (1.234,56 € -> 1234.56).",
        "- One entry in `lines` per concept. When a line shows no quantity, use quantity 1 and "
        "the line amount as unit price. When the invoice has no detailed lines, record a single "
        "line with a short description of what was invoiced and the taxable base. Record "
        "general discounts as a line with a negative unit price.",
        "- Every line carries the VAT (or IGIC) rate it is taxed at. When the invoice only "
        "shows one rate for everything, apply it to every line.",
        "- IRPF withholding is a percentage of the taxable base deducted from the total; "
        "report it as a positive percentage.",
    ]
)


def _instructions(customer: Issuer | None, *, schema_in_prompt: bool) -> str:
    text = "Record the data of this supplier invoice."
    if customer is not None:
        text += (
            f" It should be addressed to {customer.full_name} (tax id "
            f"{customer.document_number}): that is the customer, the supplier is the other party."
        )
    if schema_in_prompt:
        text += (
            " Answer with a single JSON object, and nothing else, following this JSON "
            f"schema:\n{json.dumps(INVOICE_SCHEMA, ensure_ascii=False)}"
        )
    return text


def pdf_text(pdf: bytes) -> str:
    """The text layer of the PDF (first pages only), for models that cannot read PDF files.
    Raises ``UnreadablePdf`` when the file cannot be opened or has no text (a scan)."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(pdf))
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_TEXT_PAGES]]
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        raise UnreadablePdf("not_pdf", "The file is not a readable PDF") from exc
    text = "\n\n".join(page.strip() for page in pages if page.strip())[:MAX_TEXT_CHARS]
    if not text:
        raise UnreadablePdf(
            "no_text",
            "The PDF has no text (a scan?) and the configured model cannot read PDF files",
        )
    return text


def _json_object(content: Any) -> dict[str, Any]:
    """The JSON object in a model's answer, tolerating code fences or text around it."""
    if not isinstance(content, str):
        raise ExtractionError("The model gave no answer")
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        raise ExtractionError("The model did not answer with JSON")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExtractionError("The model did not answer with valid JSON") from exc
    if not isinstance(data, dict):
        raise ExtractionError("The model did not answer with a JSON object")
    return data


class LiteLLMInvoiceExtractor:
    """Reads the invoice with any LLM LiteLLM supports.

    - Models that can read PDF files (Claude, GPT-4o, Gemini...) get the PDF itself, so
      scans work too; the others get its text layer (see ``pdf_text``).
    - Models with structured output get ``INVOICE_SCHEMA`` as the required answer format;
      the others get it in the prompt. Either way the answer is parsed leniently.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None,
        api_base: str | None,
        timeout: float,
        retries: int = 2,
        capabilities_model: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or None
        self.api_base = api_base or None
        self.timeout = timeout
        self.retries = retries
        # The catalogue name of the model, when the call uses another one (an Azure
        # deployment runs one of the catalogue's models under a name of its own)
        self.capabilities_model = capabilities_model or model
        # Vendor-specific parameters: `api_version` (Azure), `aws_region_name` (Bedrock)
        self.params = dict(params or {})
        self.litellm = import_litellm()
        self.reads_pdf = self._supports("supports_pdf_input")
        self.structured = self._supports("supports_response_schema")

    def _supports(self, capability: str) -> bool:
        """What LiteLLM knows about the model; unknown models are assumed basic."""
        from litellm import utils

        try:
            return bool(getattr(utils, capability)(model=self.capabilities_model))
        except Exception:  # noqa: BLE001 -- unknown model / provider: be conservative
            return False

    def _document(self, pdf: bytes) -> dict[str, Any]:
        if self.reads_pdf:
            data = base64.standard_b64encode(pdf).decode("ascii")
            return {
                "type": "file",
                "file": {
                    "file_data": f"data:application/pdf;base64,{data}",
                    "filename": "invoice.pdf",
                },
            }
        return {"type": "text", "text": f"Text of the invoice:\n\n{pdf_text(pdf)}"}

    async def extract(self, pdf: bytes, *, customer: Issuer | None) -> dict[str, Any]:
        document = self._document(pdf)  # UnreadablePdf before anything is sent
        options: dict[str, Any] = {}
        if self.structured:
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": SCHEMA_NAME, "schema": INVOICE_SCHEMA, "strict": False},
            }
        instructions = _instructions(customer, schema_in_prompt=not self.structured)
        try:
            response = await self.litellm.acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [document, {"type": "text", "text": instructions}]},
                ],
                temperature=0,
                max_tokens=8192,
                timeout=self.timeout,
                num_retries=self.retries,
                api_key=self.api_key,
                api_base=self.api_base,
                drop_params=True,  # a vendor that does not take a parameter simply ignores it
                **self.params,
                **options,
            )
        except Exception as exc:  # noqa: BLE001 -- LiteLLM raises a different class per vendor
            # Never log the invoice itself: it holds third-party personal and financial data.
            logger.warning("Invoice extraction with %s failed: %s", self.model, type(exc).__name__)
            raise ExtractionError("The invoice could not be read") from exc

        choice = response.choices[0]
        if choice.finish_reason == "length":
            logger.warning("Invoice extraction with %s was truncated", self.model)
        return _json_object(choice.message.content)


async def get_invoice_extractor(
    tenant: CurrentTenant, session: Annotated[AsyncSession, Depends(get_session)]
) -> InvoiceExtractor | None:
    """FastAPI dependency: an extractor with the tenant's AI settings, or None while the
    tenant has not set them up (PDF import unavailable). `503` when the stored API key can no
    longer be decrypted (the server's encryption keys changed): it must be entered again."""
    settings = await AiSettingsRepository(session, tenant.id).get()
    if settings is None:
        return None
    try:
        connection = connection_for(settings, get_secret_box())
    except SecretDecryptionError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The API key of the AI settings cannot be decrypted: enter it again",
        ) from exc
    return LiteLLMInvoiceExtractor(
        connection.model,
        api_key=connection.api_key,
        api_base=connection.api_base,
        timeout=get_settings().llm_timeout,
        capabilities_model=connection.catalog_model,
        params=connection.params,
    )


# -- from the raw answer to a draft -------------------------------------------------------

_DNI_OR_NIE_SHAPE = re.compile(r"^(\d{8}|[XYZ]\d{7})[A-Z]$")
_CIF_SHAPE = re.compile(r"^[A-Z]\d{7}[0-9A-J]$")


def _text(value: Any, limit: int) -> str:
    if isinstance(value, str):
        return " ".join(value.split())[:limit]
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)[:limit]
    return ""


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.replace("€", "").replace(" ", "")
        if "," in value:  # Spanish notation: 1.234,56
            value = value.replace(".", "").replace(",", ".")
    elif not isinstance(value, int | float):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _amount(value: Any) -> Decimal | None:
    number = _decimal(value)
    if number is None or abs(number) > MAX_AMOUNT:
        return None
    return _cents(number)


def _rate(value: Any) -> Decimal | None:
    number = _decimal(value)
    if number is None:
        return None
    number = abs(number)
    return _cents(number) if number <= 100 else None


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _tax_id(value: Any) -> str:
    """Normalised tax id; a Spanish one printed as an intra-community VAT number
    (``ESB12345674``) loses its ``ES`` prefix."""
    number = spanish_ids.normalise(_text(value, 100))
    if number.startswith("ES") and _classify(number[2:]) is not DocumentType.OTHER:
        return number[2:]
    return number


def _classify(number: str) -> DocumentType:
    """NIF / CIF when the number is one (a misread check character still counts, so that
    the form flags it for correction), OTHER for anything else (foreign ids)."""
    if spanish_ids.is_valid_nif(number) or _DNI_OR_NIE_SHAPE.match(number):
        return DocumentType.NIF
    if spanish_ids.is_valid_cif(number) or _CIF_SHAPE.match(number):
        return DocumentType.CIF
    return DocumentType.OTHER


def _country(value: Any) -> str:
    code = _text(value, 2).upper()
    if geo.find_country(code) is not None:
        return code
    return "ES"  # the usual case, and the form's default


def _province(country: str, postal_code: str, value: Any) -> str:
    raw = _text(value, 100)
    if country == "ES" and (province := geo.spanish_province_of_postal_code(postal_code)):
        return province.name
    if raw and (province := geo.find_province(country, raw)):
        return province.name
    # Unknown to the reference data: the user picks it (countries without provinces keep it)
    return "" if geo.provinces(country) else raw


def _party_draft(raw: Any) -> PartyDraft:
    raw = raw if isinstance(raw, dict) else {}
    postal_code = _text(raw.get("postal_code"), 50)
    country = _country(raw.get("country_code"))
    number = _tax_id(raw.get("tax_id"))
    return PartyDraft(
        full_name=_text(raw.get("name"), 255),
        document=IdentificationDocumentSchema(type=_classify(number), number=number),
        address=AddressSchema(
            street=_text(raw.get("street"), 255),
            zip_code=postal_code,
            city=_text(raw.get("city"), 100),
            province=_province(country, postal_code, raw.get("province")),
            country_iso_code=country,
        ),
    )


def _lines(raw: Any) -> list[InvoiceLineBase]:
    lines = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        description = _text(item.get("description"), 255)
        quantity = _decimal(item.get("quantity"))
        if quantity is None or quantity == 0 or abs(quantity) > MAX_AMOUNT:
            quantity = Decimal(1)
        unit_price = _decimal(item.get("unit_price"))
        if unit_price is None and (amount := _decimal(item.get("amount"))) is not None:
            unit_price = amount / quantity
        if unit_price is None or abs(unit_price) > MAX_AMOUNT:
            if not description:
                continue
            unit_price = Decimal(0)
        lines.append(
            InvoiceLineBase(
                description=description,
                quantity=_cents(quantity),
                unit_price=_cents(unit_price),
                tax_rate=_rate(item.get("vat_rate")) or Decimal("0.00"),
            )
        )
    return lines[:MAX_LINES]


def _addressed_to(customer_tax_id: str, account: FiscalData | None) -> bool | None:
    if account is None or not customer_tax_id:
        return None
    return customer_tax_id == _tax_id(account.document.number)


def draft_from(raw: dict[str, Any], account: FiscalData | None) -> ReceivedInvoiceDraft:
    """The form pre-fill for the raw extraction ``raw``. ``account`` (the tenant's fiscal
    data) is used to tell whether the invoice is addressed to the tenant."""
    number = _text(raw.get("invoice_number"), 100)
    payment = raw.get("payment_method")
    customer = raw.get("customer") if isinstance(raw.get("customer"), dict) else {}
    return ReceivedInvoiceDraft(
        issuer=_party_draft(raw.get("supplier")),
        invoice_number=ReceivedInvoiceNumberWrite(number=number) if number else None,
        issue_date=_date(raw.get("issue_date")),
        due_date=_date(raw.get("due_date")),
        payment_method=payment if payment in PaymentMethod.__members__ else None,
        retention_rate=_rate(raw.get("irpf_rate")) or Decimal("0.00"),
        lines=_lines(raw.get("lines")),
        printed_total=_amount(raw.get("total")),
        customer_name=_text(customer.get("name"), 255) or None,
        addressed_to_account=_addressed_to(_tax_id(customer.get("tax_id")), account),
    )

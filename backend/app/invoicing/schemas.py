"""Pydantic schemas: the public API contract of the Invoicing module.

JSON uses camelCase keys (the frontend is TypeScript); Python attributes stay snake_case.
Monetary amounts are validated as decimals (max. two places) and serialised as JSON
numbers (e.g. 120.98).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import (
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
    model_validator,
)

from app.core.schemas import ApiModel
from app.geo import service as geo
from app.invoicing import spanish_ids
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.money import bcmul
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.value_objects import InvoiceNumber


def _as_number(value: Decimal) -> float:
    return float(value)


# Decimal amounts: validated with at most two decimals, rendered as JSON numbers.
_DecimalJson = PlainSerializer(_as_number, return_type=float, when_used="json")
Money = Annotated[Decimal, Field(decimal_places=2, examples=[120.98]), _DecimalJson]
Rate = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2, examples=[21]), _DecimalJson]


# -- value objects --------------------------------------------------------------------


class InvoiceNumberSchema(ApiModel):
    """An assigned invoice number (drafts have none: the field is `null`)."""

    prefix: str = Field(default="", max_length=100, examples=["F-2026-"])
    number: str = Field(min_length=1, max_length=100, examples=["42"])
    suffix: str = Field(default="", max_length=100, examples=[""])

    @computed_field(examples=["F-2026-42"])  # type: ignore[prop-decorator]
    @property
    def formatted(self) -> str:
        return f"{self.prefix}{self.number}{self.suffix}"


# -- serial ---------------------------------------------------------------------------

# Letters, digits and the usual separators. Blanks are not allowed: they would make the
# rendered number ambiguous.
SERIAL_PART_PATTERN = r"^[A-Za-z0-9._/-]*$"
SerialPart = Annotated[
    str,
    Field(default="", max_length=100, pattern=SERIAL_PART_PATTERN, examples=["F-2026-"]),
]


class SerialWrite(ApiModel):
    """A numbering series: `prefix` + sequential number + `suffix`. At least one of prefix
    and suffix is required. Leave the dates empty for a serial without time limits."""

    prefix: SerialPart
    suffix: SerialPart
    initial_number: int = Field(default=1, ge=1, examples=[1])
    start_date: date | None = Field(default=None, description="First issue date allowed")
    end_date: date | None = Field(default=None, description="Last issue date allowed")

    @model_validator(mode="after")
    def _check_consistency(self) -> "SerialWrite":
        if not self.prefix and not self.suffix:
            raise ValueError("a prefix or a suffix is required")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("endDate cannot be earlier than startDate")
        return self


class SerialRead(SerialWrite):
    id: int
    issued_count: int = Field(description="Issued invoices numbered with this serial")
    next_number: int = Field(description="The number the next invoice issued with it gets")

    @computed_field(examples=["F-2026-43"])  # type: ignore[prop-decorator]
    @property
    def next_number_formatted(self) -> str:
        return f"{self.prefix}{self.next_number}{self.suffix}"

    @computed_field(  # type: ignore[prop-decorator]
        description="Prefix, suffix and initial number are frozen once the serial is in use"
    )
    @property
    def locked(self) -> bool:
        return self.issued_count > 0


class IdentificationDocumentSchema(ApiModel):
    type: DocumentType = DocumentType.NIF
    number: str = Field(default="", max_length=100, examples=["B12345678"])


class AddressSchema(ApiModel):
    street: str = Field(default="", max_length=255, examples=["Calle Mayor 1"])
    zip_code: str = Field(default="", max_length=50, examples=["28001"])
    city: str = Field(default="", max_length=100, examples=["Madrid"])
    province: str = Field(default="", max_length=100, examples=["Madrid"])
    country_iso_code: str = Field(default="ES", min_length=2, max_length=2, examples=["ES"])


# -- validated parties (clients, suppliers) --------------------------------------------


class PartyDocumentSchema(IdentificationDocumentSchema):
    """Identification of a client or supplier. NIF (DNI / NIE) and CIF numbers are
    normalised (upper-case, no blanks or hyphens) and their check character verified;
    `OTHER` accepts any (foreign) identifier."""

    number: str = Field(min_length=1, max_length=100, examples=["B12345674"])

    @model_validator(mode="after")
    def _check_number(self) -> "PartyDocumentSchema":
        if self.type is DocumentType.OTHER:
            return self
        number = spanish_ids.normalise(self.number)
        if self.type is DocumentType.NIF and not spanish_ids.is_valid_nif(number):
            raise ValueError("not a valid NIF (DNI or NIE): check the digits and the letter")
        if self.type is DocumentType.CIF and not spanish_ids.is_valid_cif(number):
            raise ValueError(
                "not a valid CIF: check the letter, the digits and the control character"
            )
        self.number = number
        return self


class PartyAddressSchema(AddressSchema):
    """Postal address of a client or supplier: every part is required. The country must be
    an ISO 3166-1 code, the postal code must match the country's format and the province
    must be one of the country's (when the country has any)."""

    street: str = Field(min_length=3, max_length=255, examples=["Calle Mayor 1"])
    zip_code: str = Field(min_length=1, max_length=50, examples=["28001"])
    city: str = Field(min_length=1, max_length=100, examples=["Madrid"])
    province: str = Field(min_length=1, max_length=100, examples=["Madrid"])
    country_iso_code: str = Field(
        default="ES", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$", examples=["ES"]
    )

    @field_validator("country_iso_code")
    @classmethod
    def _known_country(cls, value: str) -> str:
        value = value.upper()
        if geo.find_country(value) is None:
            raise ValueError("unknown country code")
        return value

    @model_validator(mode="after")
    def _check_against_country(self) -> "PartyAddressSchema":
        if not geo.postal_code_matches(self.country_iso_code, self.zip_code):
            raise ValueError("the postal code does not match the format of the country")
        if geo.provinces(self.country_iso_code):
            province = geo.find_province(self.country_iso_code, self.province)
            if province is None:
                raise ValueError("the province is not one of the country's provinces")
            self.province = province.name
        return self


class PartyWrite(ApiModel):
    """A counterpart of the tenant (a client, or the supplier of a received invoice):
    name, identification and address, all of them required and checked."""

    full_name: str = Field(min_length=2, max_length=255, examples=["Tech Solutions SL"])
    document: PartyDocumentSchema
    address: PartyAddressSchema


# -- fiscal data / issuer -------------------------------------------------------------


class FiscalDocumentSchema(IdentificationDocumentSchema):
    """Identification of the tenant itself: the number is mandatory."""

    number: str = Field(min_length=1, max_length=100, examples=["B12345674"])

    @field_validator("number")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class FiscalAddressSchema(AddressSchema):
    """Fiscal address of the tenant: street, postal code, city and country are mandatory."""

    street: str = Field(min_length=1, max_length=255, examples=["Calle Mayor 1"])
    zip_code: str = Field(min_length=1, max_length=50, examples=["28001"])
    city: str = Field(min_length=1, max_length=100, examples=["Madrid"])
    country_iso_code: str = Field(
        default="ES", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$", examples=["ES"]
    )

    @field_validator("country_iso_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class FiscalDataWrite(ApiModel):
    """The tenant's identity as invoice issuer."""

    company_name: str = Field(min_length=1, max_length=255, examples=["Mi Empresa S.L."])
    document: FiscalDocumentSchema
    address: FiscalAddressSchema


class FiscalDataRead(FiscalDataWrite):
    pass


class IssuerRead(ApiModel):
    """The issuer as stored on an invoice: a copy of the fiscal data at that time (issued
    invoices) or the supplier as entered (received invoices)."""

    full_name: str
    document: IdentificationDocumentSchema
    address: AddressSchema


# -- subject --------------------------------------------------------------------------


class SubjectRead(ApiModel):
    """The recipient as stored on an invoice: for an issued invoice, a copy of the client
    taken when it was created (or the draft last re-pointed at a client); for a received
    one, a copy of the account's fiscal data."""

    id: int
    full_name: str = Field(max_length=255, examples=["Tech Solutions SL"])
    document: IdentificationDocumentSchema
    address: AddressSchema


# -- invoice line ---------------------------------------------------------------------


class InvoiceLineBase(ApiModel):
    description: str = Field(default="", max_length=255, examples=["Consultoría"])
    quantity: Money = Decimal("1.00")
    unit_price: Money = Decimal("0.00")
    tax_rate: Rate = Decimal("0.00")


class InvoiceLineCreate(InvoiceLineBase):
    # Every stored line needs a concept, whatever the state of the invoice.
    description: str = Field(min_length=1, max_length=255, examples=["Consultoría"])


class InvoiceLineRead(InvoiceLineBase):
    id: int
    subtotal: Money
    tax_amount: Money
    total: Money


# -- invoice --------------------------------------------------------------------------


class InvoiceContent(ApiModel):
    """What issued and received invoices share: dates, payment, notes, IRPF retention and
    lines, with the rules that apply to both."""

    issue_date: date = Field(default_factory=date.today, description="Cannot be in the future")
    notes: str = Field(default="", max_length=5000)
    due_date: date | None = Field(default=None, description="Cannot be earlier than the issue date")
    payment_method: PaymentMethod = PaymentMethod.TRANSFER
    retention_rate: Rate = Field(
        default=Decimal("0.00"),
        description="IRPF withholding on the whole invoice (% of the subtotal, deducted)",
    )
    lines: list[InvoiceLineCreate] = Field(min_length=1, description="At least one line")

    @model_validator(mode="after")
    def _check_consistency(self) -> "InvoiceContent":
        """Rules shared by every invoice, draft or not (the same record ends up stored)."""
        if self.issue_date > date.today():
            raise ValueError("issueDate cannot be in the future")
        if self.due_date is not None and self.due_date < self.issue_date:
            raise ValueError("dueDate cannot be earlier than issueDate")
        subtotal = sum(
            (bcmul(line.quantity, line.unit_price, 2) for line in self.lines), Decimal(0)
        )
        if subtotal <= 0:
            raise ValueError("the invoice must have a positive amount")
        return self


class InvoiceWrite(InvoiceContent):
    """Fields accepted when creating or replacing an issued invoice. The issuer is not part
    of the payload: it is always the fiscal data of the account."""

    state: InvoiceState = Field(
        default=InvoiceState.DRAFT,
        description="Lifecycle state. New invoices start as DRAFT unless stated otherwise.",
    )
    serial_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "The serial the invoice number is taken from. Required to issue; a draft may "
            "carry it to remember the choice."
        ),
    )
    client_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "The client whose data is copied as recipient. Required when creating; on a "
            "draft update it replaces the recipient, and omitting it keeps the current one."
        ),
    )


class InvoiceCreate(InvoiceWrite):
    client_id: int = Field(gt=0, description="The client whose data is copied as recipient")


class InvoiceUpdate(InvoiceWrite):
    """Full replacement of a draft invoice (its lines included)."""


class ReceivedInvoiceNumberWrite(ApiModel):
    """The number printed on a supplier's invoice, whole and as printed (any series, prefix
    or suffix included: which part is which is the supplier's business)."""

    number: str = Field(min_length=1, max_length=100, examples=["FV-2026/0042"])


class ReceivedInvoiceWrite(InvoiceContent):
    """Fields accepted when creating or replacing a received invoice (an expense). The
    supplier and its invoice number are entered by hand; the recipient is not part of the
    payload: it is always the fiscal data of the account. There is no `state`: a received
    invoice has already been issued (by its supplier) and is stored as such."""

    issuer: PartyWrite = Field(description="The supplier who issued the invoice")
    invoice_number: ReceivedInvoiceNumberWrite = Field(
        description="The supplier's series and number, as printed on its invoice"
    )


class ReceivedInvoiceCreate(ReceivedInvoiceWrite):
    pass


class ReceivedInvoiceUpdate(ReceivedInvoiceWrite):
    """Full replacement of a received invoice (its lines included). Received invoices can
    always be edited."""


class PartyDraft(ApiModel):
    """A party as read from a document: any field may be empty."""

    full_name: str = ""
    document: IdentificationDocumentSchema
    address: AddressSchema


class ReceivedInvoiceDraft(ApiModel):
    """What could be read from the PDF of a received invoice, to pre-fill the form. Nothing
    is stored: once reviewed, it is saved with `POST /api/received-invoice`. Whatever could
    not be read is empty / `null`."""

    issuer: PartyDraft = Field(description="The supplier")
    invoice_number: ReceivedInvoiceNumberWrite | None
    issue_date: date | None
    due_date: date | None
    payment_method: PaymentMethod | None
    retention_rate: Rate
    lines: list[InvoiceLineBase]
    printed_total: Money | None = Field(
        description="The total printed on the invoice, to check the lines against"
    )
    customer_name: str | None = Field(description="Who the invoice is addressed to")
    addressed_to_account: bool | None = Field(
        description=(
            "Whether the invoice is addressed to the account (the customer's NIF / CIF is the "
            "one in the fiscal data); `null` when it cannot be told"
        )
    )


class InvoiceRead(ApiModel):
    id: int
    kind: InvoiceKind = Field(
        description="ISSUED (income, to a client) or RECEIVED (expense, from a supplier)"
    )
    issue_date: date
    invoice_number: InvoiceNumberSchema | None = Field(
        description="`null` while an issued invoice is a draft"
    )
    serial_id: int | None = Field(description="Always `null` on received invoices")
    state: InvoiceState = Field(
        description=(
            "Issued invoices: DRAFT, then ISSUED (immutable). Received invoices: always ISSUED "
            "(by their supplier), and editable"
        )
    )
    issuer: IssuerRead = Field(
        description="Issued: the account's fiscal data. Received: the supplier."
    )
    recipient: SubjectRead = Field(
        description="Issued: a copy of the client. Received: the account's fiscal data."
    )
    notes: str
    due_date: date | None
    collected_on: date | None = Field(
        description=(
            "Issued invoices: the day the client paid it, `null` while pending collection. "
            "Always `null` on drafts and received invoices."
        )
    )
    payment_method: PaymentMethod
    retention_rate: Rate
    lines: list[InvoiceLineRead]
    subtotal: Money
    tax_amount: Money
    retention_amount: Money
    total: Money

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _unassigned_is_none(cls, value: object) -> object:
        if isinstance(value, InvoiceNumber) and not value.is_assigned:
            return None
        return value


class InvoiceCollectionStatus(ApiModel):
    """Whether an issued invoice has been collected (paid by the client), and when."""

    collected_on: date | None = Field(
        description=(
            "The day the client paid the invoice: not before its issue date nor in the future. "
            "`null` marks it as pending collection again."
        ),
        examples=["2026-03-10"],
    )

    @field_validator("collected_on")
    @classmethod
    def _not_in_the_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("collectedOn cannot be in the future")
        return value


class InvoiceCollection(ApiModel):
    items: list[InvoiceRead]
    total: int = Field(description="Total number of invoices matching the query")
    limit: int
    offset: int


# -- misc -----------------------------------------------------------------------------


class HealthStatus(ApiModel):
    status: str = "ok"
    app: str
    version: str

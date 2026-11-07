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
from app.invoicing.document_type import DocumentType
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
    """The issuer as stamped on an invoice (a copy of the fiscal data at that time)."""

    full_name: str
    document: IdentificationDocumentSchema
    address: AddressSchema


# -- subject --------------------------------------------------------------------------


class SubjectBase(ApiModel):
    full_name: str = Field(max_length=255, examples=["Tech Solutions SL"])
    document: IdentificationDocumentSchema = Field(default_factory=IdentificationDocumentSchema)
    address: AddressSchema = Field(default_factory=AddressSchema)


class SubjectCreate(SubjectBase):
    pass


class SubjectRead(SubjectBase):
    id: int


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


class InvoiceWrite(ApiModel):
    """Fields accepted when creating or replacing an invoice. The issuer is not part of the
    payload: it is always the fiscal data of the account."""

    issue_date: date = Field(default_factory=date.today, description="Cannot be in the future")
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
    recipient_id: int = Field(gt=0)
    notes: str = Field(default="", max_length=5000)
    due_date: date | None = Field(default=None, description="Cannot be earlier than the issue date")
    payment_method: PaymentMethod = PaymentMethod.TRANSFER
    retention_rate: Rate = Field(
        default=Decimal("0.00"),
        description="IRPF withholding on the whole invoice (% of the subtotal, deducted)",
    )
    lines: list[InvoiceLineCreate] = Field(min_length=1, description="At least one line")

    @model_validator(mode="after")
    def _check_consistency(self) -> "InvoiceWrite":
        """Rules shared by drafts and issued invoices (the same record ends up stored)."""
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


class InvoiceCreate(InvoiceWrite):
    pass


class InvoiceUpdate(InvoiceWrite):
    """Full replacement of a draft invoice (its lines included)."""


class InvoiceRead(ApiModel):
    id: int
    issue_date: date
    invoice_number: InvoiceNumberSchema | None = Field(description="`null` while a draft")
    serial_id: int | None
    state: InvoiceState
    issuer: IssuerRead
    recipient: SubjectRead
    notes: str
    due_date: date | None
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

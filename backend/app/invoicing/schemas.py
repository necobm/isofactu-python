"""Pydantic schemas: the public API contract of the Invoicing module.

JSON uses camelCase keys (the frontend is TypeScript); Python attributes stay snake_case.
Monetary amounts are validated as decimals (max. two places) and serialised as JSON
numbers (e.g. 120.98).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

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


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
    )


# -- value objects --------------------------------------------------------------------


class InvoiceNumberSchema(ApiModel):
    """An assigned invoice number (drafts have none: the field is `null`)."""

    serial: str | None = Field(default=None, max_length=100, examples=["F-2026"])
    number: str = Field(min_length=1, max_length=100, examples=["42"])

    @computed_field(examples=["F-2026-42"])  # type: ignore[prop-decorator]
    @property
    def formatted(self) -> str:
        return f"{self.serial}-{self.number}" if self.serial else self.number


class InvoiceNumberInput(ApiModel):
    """Number requested when issuing an invoice. Leave `number` empty to get the next
    sequential number of the serial assigned automatically."""

    serial: str | None = Field(default=None, max_length=100, examples=["F-2026"])
    number: str | None = Field(default=None, max_length=100, examples=["42"])

    @field_validator("serial", "number")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class IdentificationDocumentSchema(ApiModel):
    type: DocumentType = DocumentType.NIF
    number: str = Field(default="", max_length=100, examples=["B12345678"])


class AddressSchema(ApiModel):
    street: str = Field(default="", max_length=255, examples=["Calle Mayor 1"])
    zip_code: str = Field(default="", max_length=50, examples=["28001"])
    city: str = Field(default="", max_length=100, examples=["Madrid"])
    province: str = Field(default="", max_length=100, examples=["Madrid"])
    country_iso_code: str = Field(default="ES", min_length=2, max_length=2, examples=["ES"])


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
    """Fields accepted when creating or replacing an invoice."""

    issue_date: date = Field(default_factory=date.today, description="Cannot be in the future")
    state: InvoiceState = Field(
        default=InvoiceState.DRAFT,
        description="Lifecycle state. New invoices start as DRAFT unless stated otherwise.",
    )
    invoice_number: InvoiceNumberInput | None = Field(
        default=None,
        description=(
            "Only for ISSUED invoices (drafts are numberless). Omit `number` to have the next "
            "one in the serial assigned."
        ),
    )
    issuer_id: int = Field(gt=0)
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
    state: InvoiceState
    issuer: SubjectRead
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

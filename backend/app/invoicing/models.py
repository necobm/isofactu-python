"""ORM entities of the Invoicing module (port of the Doctrine entities).

Table / column names intentionally mirror what Doctrine's `underscore_number_aware`
naming strategy would have generated for the original PHP entities.

Every subject and invoice belongs to one tenant (its `owner`, an ADMIN user); the
repositories only ever see the rows of the current tenant.

Issued (income) and received (expense) invoices share the `invoice` table, told apart by
`Invoice.kind`: both have an issuer, a recipient, a number, a lifecycle and lines, only who
fills in each party and the number differs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, composite, mapped_column, relationship

from app.accounts.models import User
from app.core.database import Base
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_kind import InvoiceKind
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.money import bcadd, bcdiv, bcmul, bcsub
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber, Issuer


class Subject(Base):
    """The recipient of an invoice, owned by that invoice: a copy of the client's data
    (name, NIF/CIF, address) taken when an issued invoice was created, or of the tenant's
    fiscal data for a received one. Clients themselves live in the Clients module and are
    never referenced from here."""

    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, index=True
    )
    owner: Mapped[User] = relationship(repr=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    document: Mapped[IdentificationDocument] = composite(
        mapped_column(
            "document_type",
            Enum(DocumentType, name="document_type", native_enum=False, length=10),
        ),
        mapped_column("document_number", String(100), index=True),
        default_factory=IdentificationDocument,
    )
    address: Mapped[Address] = composite(
        mapped_column("address_street", String(255)),
        mapped_column("address_zip_code", String(50)),
        mapped_column("address_city", String(100)),
        mapped_column("address_province", String(100)),
        mapped_column("address_country_iso_code", String(2)),
        default_factory=Address,
    )

    def __str__(self) -> str:
        return self.full_name


class FiscalData(Base):
    """The tenant's own identity as invoice issuer (one row per account)."""

    __tablename__ = "fiscal_data"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, unique=True
    )
    owner: Mapped[User] = relationship(repr=False)
    company_name: Mapped[str] = mapped_column(String(255), default="")
    document: Mapped[IdentificationDocument] = composite(
        mapped_column(
            "document_type",
            Enum(DocumentType, name="document_type", native_enum=False, length=10),
        ),
        mapped_column("document_number", String(100)),
        default_factory=IdentificationDocument,
    )
    address: Mapped[Address] = composite(
        mapped_column("address_street", String(255)),
        mapped_column("address_zip_code", String(50)),
        mapped_column("address_city", String(100)),
        mapped_column("address_province", String(100)),
        mapped_column("address_country_iso_code", String(2)),
        default_factory=Address,
    )

    def as_issuer(self) -> Issuer:
        """The snapshot stamped on invoices."""
        return Issuer.of(self.company_name, self.document, self.address)

    def __str__(self) -> str:
        return self.company_name


class Serial(Base):
    """A numbering series of a tenant: ``prefix`` + sequential number + ``suffix``.

    Numbers start at ``initial_number`` and are correlative within the serial. The serial
    can be restricted to a period: invoices whose issue date falls outside
    ``[start_date, end_date]`` (either bound optional) cannot take a number from it.
    """

    __tablename__ = "serial"
    __table_args__ = (
        UniqueConstraint("owner_id", "prefix", "suffix"),
        CheckConstraint("prefix <> '' OR suffix <> ''", name="prefix_or_suffix"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, index=True
    )
    owner: Mapped[User] = relationship(repr=False)
    prefix: Mapped[str] = mapped_column(String(100), default="")
    suffix: Mapped[str] = mapped_column(String(100), default="")
    initial_number: Mapped[int] = mapped_column(Integer, default=1)
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)

    def is_available_on(self, day: date) -> bool:
        """Whether an invoice issued on `day` may take a number from this serial."""
        if self.start_date is not None and day < self.start_date:
            return False
        if self.end_date is not None and day > self.end_date:
            return False
        return True

    def number(self, value: int) -> InvoiceNumber:
        return InvoiceNumber(self.prefix, str(value), self.suffix)

    def __str__(self) -> str:
        return f"{self.prefix}#{self.suffix}"


class Invoice(Base):
    """Carries a copy of the issuer, links a recipient, has a date and number and holds one
    or more lines.

    Who each party is depends on the `kind`:

    - ISSUED: the issuer is a snapshot of the tenant's fiscal data and the recipient a copy
      of one of its clients; the number comes from one of the tenant's serials.
    - RECEIVED: the issuer is the supplier, entered by hand, and the recipient a copy of the
      tenant's fiscal data; the number (the supplier's) is entered by hand too, so these
      invoices never take a number from -- or lock -- a serial. They have no lifecycle:
      already issued by the supplier, they are stored as ISSUED and can always be edited.
    """

    __tablename__ = "invoice"
    __table_args__ = (
        CheckConstraint("kind = 'ISSUED' OR serial_id IS NULL", name="serial_kind"),
        CheckConstraint("kind = 'ISSUED' OR state = 'ISSUED'", name="received_state"),
        CheckConstraint(
            "kind = 'ISSUED' OR (number_prefix = '' AND number_suffix = '')",
            name="received_whole_number",
        ),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, index=True
    )
    owner: Mapped[User] = relationship(repr=False)
    # Issued invoices: snapshot of the tenant's fiscal data at the time the invoice was
    # (last) saved. Received invoices: the supplier, as entered by the user.
    issuer: Mapped[Issuer] = composite(
        mapped_column("issuer_name", String(255)),
        mapped_column(
            "issuer_document_type",
            Enum(DocumentType, name="document_type", native_enum=False, length=10),
        ),
        mapped_column("issuer_document_number", String(100)),
        mapped_column("issuer_address_street", String(255)),
        mapped_column("issuer_address_zip_code", String(50)),
        mapped_column("issuer_address_city", String(100)),
        mapped_column("issuer_address_province", String(100)),
        mapped_column("issuer_address_country_iso_code", String(2)),
    )
    recipient_id: Mapped[int] = mapped_column(ForeignKey("subject.id"), init=False, index=True)
    recipient: Mapped[Subject] = relationship(foreign_keys=[recipient_id], lazy="joined")
    kind: Mapped[InvoiceKind] = mapped_column(
        Enum(InvoiceKind, name="invoice_kind", native_enum=False, length=10),
        default=InvoiceKind.ISSUED,
        index=True,
    )

    issue_date: Mapped[date] = mapped_column(Date, default_factory=date.today, index=True)
    # Issued invoices: unassigned (`number` NULL) while a draft; prefix and suffix are a copy
    # of the serial's at the time of issuing. Received invoices: the supplier's number, whole
    # and as printed, in `number` (prefix and suffix stay empty).
    invoice_number: Mapped[InvoiceNumber] = composite(
        mapped_column("number_prefix", String(100)),
        mapped_column("number", String(100), nullable=True),
        mapped_column("number_suffix", String(100)),
        default_factory=InvoiceNumber,
    )
    # The serial the number was (or, for a draft, will be) taken from. Serials used by an
    # issued invoice cannot be deleted. Always NULL on received invoices.
    serial_id: Mapped[int | None] = mapped_column(ForeignKey("serial.id"), default=None, index=True)
    state: Mapped[InvoiceState] = mapped_column(
        Enum(InvoiceState, name="invoice_state", native_enum=False, length=10),
        default=InvoiceState.DRAFT,
        index=True,
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", native_enum=False, length=20),
        default=PaymentMethod.TRANSFER,
    )
    # IRPF withholding applied to the whole invoice (Spanish freelancers): a percentage of
    # the subtotal that the recipient keeps back, so it is deducted from the total.
    retention_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLine.id",
        lazy="selectin",
        default_factory=list,
    )

    # -- line management -------------------------------------------------------------

    def add_line(self, line: InvoiceLine) -> Invoice:
        if line not in self.lines:
            self.lines.append(line)
            line.invoice = self
        return self

    def remove_line(self, line: InvoiceLine) -> Invoice:
        if line in self.lines:
            self.lines.remove(line)
            if line.invoice is self:
                line.invoice = None
        return self

    # -- computed amounts ------------------------------------------------------------

    @property
    def subtotal(self) -> Decimal:
        return sum((line.subtotal for line in self.lines), Decimal("0.00"))

    @property
    def tax_amount(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines), Decimal("0.00"))

    @property
    def retention_amount(self) -> Decimal:
        return bcmul(self.subtotal, bcdiv(self.retention_rate, 100, 4), 2)

    @property
    def total(self) -> Decimal:
        lines_total = sum((line.total for line in self.lines), Decimal("0.00"))
        return bcsub(lines_total, self.retention_amount, 2)

    def __str__(self) -> str:
        return str(self.invoice_number) if self.invoice_number.is_assigned else "(draft)"


class InvoiceLine(Base):
    """A concept of an invoice: description, quantity, unit price and tax rate."""

    __tablename__ = "invoice_line"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoice.id", ondelete="CASCADE"), init=False, index=True
    )
    invoice: Mapped[Invoice | None] = relationship(back_populates="lines", default=None)

    description: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))

    @property
    def subtotal(self) -> Decimal:
        return bcmul(self.quantity, self.unit_price, 2)

    @property
    def tax_amount(self) -> Decimal:
        return bcmul(self.subtotal, bcdiv(self.tax_rate, 100, 4), 2)

    @property
    def total(self) -> Decimal:
        return bcadd(self.subtotal, self.tax_amount, 2)

    def __str__(self) -> str:
        return self.description

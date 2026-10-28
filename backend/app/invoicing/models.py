"""ORM entities of the Invoicing module (port of the Doctrine entities).

Table / column names intentionally mirror what Doctrine's `underscore_number_aware`
naming strategy would have generated for the original PHP entities.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, composite, mapped_column, relationship

from app.core.database import Base
from app.invoicing.document_type import DocumentType
from app.invoicing.invoice_state import InvoiceState
from app.invoicing.money import bcadd, bcdiv, bcmul, bcsub
from app.invoicing.payment_method import PaymentMethod
from app.invoicing.value_objects import Address, IdentificationDocument, InvoiceNumber


class Subject(Base):
    """A company or person identified by NIF/CIF acting as issuer or recipient."""

    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
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


class Invoice(Base):
    """Links an issuer and a recipient, has a date and number and holds one or more lines."""

    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    issuer_id: Mapped[int] = mapped_column(ForeignKey("subject.id"), init=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("subject.id"), init=False, index=True)

    issuer: Mapped[Subject] = relationship(foreign_keys=[issuer_id], lazy="joined")
    recipient: Mapped[Subject] = relationship(foreign_keys=[recipient_id], lazy="joined")

    issue_date: Mapped[date] = mapped_column(Date, default_factory=date.today, index=True)
    # Unassigned (both columns NULL) while the invoice is a draft.
    invoice_number: Mapped[InvoiceNumber] = composite(
        mapped_column("serial", String(100), nullable=True),
        mapped_column("number", String(100), nullable=True),
        default_factory=InvoiceNumber,
    )
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

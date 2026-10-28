"""Value objects of the Invoicing module.

They are immutable dataclasses mapped as SQLAlchemy *composites* (the equivalent of
Doctrine embeddables): each one is stored as a group of columns on the owning table.
The positional order of the fields MUST match the order of the mapped columns.
"""

from dataclasses import dataclass

from app.invoicing.document_type import DocumentType


@dataclass(frozen=True, slots=True)
class InvoiceNumber:
    """Invoice identifier made of an optional serial plus a sequential number.

    Draft invoices carry no number yet: ``InvoiceNumber()`` is the *unassigned* value
    (``is_assigned`` is false and it renders as an empty string).
    """

    serial: str | None = None
    number: str | None = None

    @property
    def is_assigned(self) -> bool:
        return bool(self.number)

    def __str__(self) -> str:
        if not self.is_assigned:
            return ""
        if self.serial:
            return f"{self.serial}-{self.number}"
        return str(self.number)


@dataclass(frozen=True, slots=True)
class IdentificationDocument:
    """NIF / CIF (or other) identification of a Subject."""

    type: DocumentType = DocumentType.NIF
    number: str = ""

    def __str__(self) -> str:
        return f"{self.type.value}: {self.number}"


@dataclass(frozen=True, slots=True)
class Address:
    street: str = ""
    zip_code: str = ""
    city: str = ""
    province: str = ""
    country_iso_code: str = "ES"

    def __str__(self) -> str:
        return (
            f"{self.street}, {self.zip_code} {self.city}, {self.province} ({self.country_iso_code})"
        )

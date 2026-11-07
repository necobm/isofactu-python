"""ORM entities of the Clients module."""

from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, composite, mapped_column, relationship

from app.accounts.models import User
from app.core.database import Base
from app.invoicing.document_type import DocumentType
from app.invoicing.value_objects import Address, IdentificationDocument


class Client(Base):
    """A company or person the tenant issues invoices to.

    Carries exactly what an invoice needs about its recipient. Invoices do not point at
    clients: they keep their own copy (`Subject`), so a client can be edited or deleted
    without touching any invoice.
    """

    __tablename__ = "client"

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

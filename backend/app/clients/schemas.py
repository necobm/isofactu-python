"""Pydantic schemas of the Clients module (API contract, camelCase JSON)."""

from pydantic import Field

from app.core.schemas import ApiModel
from app.invoicing.schemas import AddressSchema, IdentificationDocumentSchema


class ClientWrite(ApiModel):
    """What an invoice needs about its recipient. Only the name is mandatory."""

    full_name: str = Field(min_length=1, max_length=255, examples=["Tech Solutions SL"])
    document: IdentificationDocumentSchema = Field(default_factory=IdentificationDocumentSchema)
    address: AddressSchema = Field(default_factory=AddressSchema)


class ClientCreate(ClientWrite):
    pass


class ClientUpdate(ClientWrite):
    """Full replacement of a client."""


class ClientRead(ClientWrite):
    id: int


class ClientCollection(ApiModel):
    items: list[ClientRead]
    total: int = Field(description="Total number of clients matching the query")
    limit: int
    offset: int

"""Pydantic schemas of the Clients module (API contract, camelCase JSON).

Everything an invoice needs about its recipient is mandatory and checked: the name, a
well-formed NIF / CIF, and an address whose country, postal code and province are
validated against the reference data of the Geo module.
"""

from pydantic import Field

from app.core.schemas import ApiModel
from app.invoicing.schemas import (
    AddressSchema,
    IdentificationDocumentSchema,
    PartyAddressSchema,
    PartyDocumentSchema,
    PartyWrite,
)

# The validation rules are shared with the suppliers of received invoices (Invoicing module).
ClientDocumentSchema = PartyDocumentSchema
ClientAddressSchema = PartyAddressSchema


class ClientWrite(PartyWrite):
    """What an invoice needs about its recipient: all of it is required."""


class ClientCreate(ClientWrite):
    pass


class ClientUpdate(ClientWrite):
    """Full replacement of a client."""


class ClientRead(ApiModel):
    id: int
    full_name: str
    document: IdentificationDocumentSchema
    address: AddressSchema


class ClientCollection(ApiModel):
    items: list[ClientRead]
    total: int = Field(description="Total number of clients matching the query")
    limit: int
    offset: int

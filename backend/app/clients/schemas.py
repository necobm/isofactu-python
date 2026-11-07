"""Pydantic schemas of the Clients module (API contract, camelCase JSON).

Everything an invoice needs about its recipient is mandatory and checked: the name, a
well-formed NIF / CIF, and an address whose country, postal code and province are
validated against the reference data of the Geo module.
"""

from pydantic import Field, field_validator, model_validator

from app.core.schemas import ApiModel
from app.geo import service as geo
from app.invoicing import spanish_ids
from app.invoicing.document_type import DocumentType
from app.invoicing.schemas import AddressSchema, IdentificationDocumentSchema


class ClientDocumentSchema(IdentificationDocumentSchema):
    """Identification of a client. NIF (DNI / NIE) and CIF numbers are normalised
    (upper-case, no blanks or hyphens) and their check character verified."""

    number: str = Field(min_length=1, max_length=100, examples=["B12345674"])

    @model_validator(mode="after")
    def _check_number(self) -> "ClientDocumentSchema":
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


class ClientAddressSchema(AddressSchema):
    """Postal address of a client: every part is required. The country must be an ISO
    3166-1 code, the postal code must match the country's format and the province must be
    one of the country's (when the country has any)."""

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
    def _check_against_country(self) -> "ClientAddressSchema":
        if not geo.postal_code_matches(self.country_iso_code, self.zip_code):
            raise ValueError("the postal code does not match the format of the country")
        if geo.provinces(self.country_iso_code):
            province = geo.find_province(self.country_iso_code, self.province)
            if province is None:
                raise ValueError("the province is not one of the country's provinces")
            self.province = province.name
        return self


class ClientWrite(ApiModel):
    """What an invoice needs about its recipient: all of it is required."""

    full_name: str = Field(min_length=2, max_length=255, examples=["Tech Solutions SL"])
    document: ClientDocumentSchema
    address: ClientAddressSchema


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

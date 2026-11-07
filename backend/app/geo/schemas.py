"""Pydantic schemas of the Geo module."""

from app.core.schemas import ApiModel


class CountryRead(ApiModel):
    code: str
    name: str
    postal_code_pattern: str | None


class ProvinceRead(ApiModel):
    code: str
    name: str

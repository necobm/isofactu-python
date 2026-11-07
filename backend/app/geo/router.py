"""HTTP endpoints of the Geo module: reference data for address forms (any session)."""

from fastapi import APIRouter, HTTPException, status

from app.accounts.deps import CurrentUser
from app.geo import service
from app.geo.schemas import CountryRead, ProvinceRead

geo_router = APIRouter(prefix="/geo", tags=["Geo"])


@geo_router.get(
    "/countries",
    response_model=list[CountryRead],
    summary="List countries",
    description="Every ISO 3166-1 country, named in Spanish, with its postal code pattern.",
)
async def list_countries(_: CurrentUser) -> list[CountryRead]:
    return [CountryRead.model_validate(c) for c in service.countries()]


@geo_router.get(
    "/countries/{country_code}/provinces",
    response_model=list[ProvinceRead],
    summary="List the provinces of a country",
    description=(
        "The lowest-level ISO 3166-2 divisions of the country (Spain: its provinces). Empty "
        "for countries without any, in which case the province is free text."
    ),
)
async def list_provinces(_: CurrentUser, country_code: str) -> list[ProvinceRead]:
    _country(country_code)
    return [ProvinceRead.model_validate(p) for p in service.provinces(country_code)]


@geo_router.get(
    "/countries/{country_code}/provinces/{province_code}/cities",
    response_model=list[str],
    summary="List the known localities of a province",
    description=(
        "Suggestions for the city field. Spanish localities come from GeoNames, which only "
        "records their autonomous community, so the list covers the whole community of the "
        "province. Empty for other countries: the city is then free text."
    ),
)
async def list_cities(_: CurrentUser, country_code: str, province_code: str) -> list[str]:
    _country(country_code)
    return list(service.cities(country_code, province_code))


def _country(code: str) -> None:
    if service.find_country(code) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Country not found")

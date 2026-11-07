"""Reference data for address forms (`/api/geo`)."""

from httpx import AsyncClient

from app.geo import service


def test_countries_are_named_in_spanish_and_sorted() -> None:
    countries = service.countries()
    assert len(countries) == 249
    names = [c.name for c in countries]
    assert names[:3] == ["Afganistán", "Albania", "Alemania"]
    spain = service.find_country("es")
    assert spain is not None and (spain.name, spain.postal_code_pattern) == ("España", r"^(\d{5})$")
    assert service.find_country("XX") is None


def test_spanish_provinces_and_cities() -> None:
    provinces = service.provinces("ES")
    assert len(provinces) == 52  # 50 provinces + Ceuta and Melilla
    names = [p.name for p in provinces]
    assert names[:2] == ["A Coruña", "Álava"]  # accent-insensitive order, brackets stripped
    assert "Barcelona" in names and "Ceuta" in names
    assert service.find_province("ES", "Lleida") is not None
    assert service.find_province("ES", "ES-GI").name == "Girona"
    assert service.find_province("ES", "Girona [Gerona]") is None

    madrid = service.cities("ES", "ES-M")
    assert "Madrid" in madrid and "Alcalá de Henares" in madrid
    # GeoNames keys Spanish localities by autonomous community: every Catalan province
    # gets the community's list
    assert service.cities("ES", "ES-B") == service.cities("ES", "ES-GI")
    assert "Barcelona" in service.cities("ES", "ES-B")
    assert service.cities("ES", "ES-XX") == ()
    assert service.provinces("VA") == () and service.cities("DE", "DE-BE") == ()


async def test_geo_endpoints(client: AsyncClient, tenant_client: AsyncClient) -> None:
    assert (await client.get("/api/geo/countries")).status_code == 401

    countries = await tenant_client.get("/api/geo/countries")
    assert countries.status_code == 200
    spain = next(c for c in countries.json() if c["code"] == "ES")
    assert spain == {"code": "ES", "name": "España", "postalCodePattern": r"^(\d{5})$"}

    provinces = await tenant_client.get("/api/geo/countries/es/provinces")
    assert provinces.status_code == 200
    assert {"code": "ES-M", "name": "Madrid"} in provinces.json()
    assert (await tenant_client.get("/api/geo/countries/XX/provinces")).status_code == 404
    assert (await tenant_client.get("/api/geo/countries/VA/provinces")).json() == []

    cities = await tenant_client.get("/api/geo/countries/ES/provinces/ES-M/cities")
    assert cities.status_code == 200 and "Madrid" in cities.json()
    assert (await tenant_client.get("/api/geo/countries/ES/provinces/ES-XX/cities")).json() == []

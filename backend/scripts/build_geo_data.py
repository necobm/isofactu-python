"""Regenerate the reference data of the `app.geo` module from GeoNames.

    pip install geonamescache
    python scripts/build_geo_data.py

Writes `app/geo/data/postal_codes.json` (postal code pattern per country) and
`app/geo/data/cities.json` (localities keyed by ISO 3166-2 subdivision). GeoNames only
records the first-level division of each locality, which for Spain is the autonomous
community, so Spanish localities are keyed by community and the service serves them for
every province of that community. Replace the file with a list keyed by province codes
(e.g. the INE municipality register) to get exact per-province lists.
"""

import json
from pathlib import Path

import geonamescache

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "geo" / "data"

# GeoNames admin1 codes of Spain -> ISO 3166-2 autonomous community codes.
SPAIN_ADMIN1 = {
    "07": "ES-IB", "27": "ES-RI", "29": "ES-MD", "31": "ES-MC", "32": "ES-NC", "34": "ES-AS",
    "39": "ES-CB", "51": "ES-AN", "52": "ES-AR", "53": "ES-CN", "54": "ES-CM", "55": "ES-CL",
    "56": "ES-CT", "57": "ES-EX", "58": "ES-GA", "59": "ES-PV", "60": "ES-VC", "CE": "ES-CE",
    "ML": "ES-ML",
}  # fmt: skip


def main() -> None:
    cache = geonamescache.GeonamesCache(min_city_population=500)
    postal = {
        code: info["postalcoderegex"]
        for code, info in cache.get_countries().items()
        if info.get("postalcoderegex")
    }
    cities: dict[str, set[str]] = {}
    for city in cache.get_cities().values():
        if city["countrycode"] != "ES":
            continue
        key = SPAIN_ADMIN1[city["admin1code"]]
        cities.setdefault(key, set()).add(city["name"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "postal_codes.json").write_text(
        json.dumps(dict(sorted(postal.items())), indent=1, ensure_ascii=False) + "\n"
    )
    (DATA_DIR / "cities.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(cities.items())}, ensure_ascii=False) + "\n"
    )
    print(
        f"{len(postal)} postal code patterns, {sum(map(len, cities.values()))} Spanish localities"
    )


if __name__ == "__main__":
    main()

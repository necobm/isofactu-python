"""Countries, first-level divisions ("provinces") and cities, for address forms.

Countries and provinces come from ISO 3166 (`pycountry`, names translated to Spanish);
postal code patterns and Spanish localities from GeoNames, pre-extracted into
`data/` by `scripts/build_geo_data.py`. Everything is loaded once and kept in memory.
"""

from __future__ import annotations

import gettext
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pycountry

DATA_DIR = Path(__file__).resolve().parent / "data"
LANGUAGE = "es"


@dataclass(frozen=True, slots=True)
class Country:
    code: str
    name: str
    postal_code_pattern: str | None


@dataclass(frozen=True, slots=True)
class Province:
    code: str
    name: str
    parent_code: str | None


def _translator(domain: str) -> gettext.NullTranslations:
    try:
        return gettext.translation(domain, pycountry.LOCALES_DIR, languages=[LANGUAGE])
    except FileNotFoundError:  # pragma: no cover - the catalogue ships with pycountry
        return gettext.NullTranslations()


def _clean(name: str) -> str:
    """ISO names sometimes carry an alternate spelling in brackets or a trailing `*`."""
    return name.split(" [")[0].rstrip("*").strip()


@cache
def _postal_code_patterns() -> dict[str, str]:
    return json.loads((DATA_DIR / "postal_codes.json").read_text())


@cache
def _cities() -> dict[str, list[str]]:
    return json.loads((DATA_DIR / "cities.json").read_text())


@cache
def countries() -> tuple[Country, ...]:
    """Every ISO 3166-1 country, named in Spanish and sorted by that name."""
    translate = _translator("iso3166-1").gettext
    patterns = _postal_code_patterns()
    items = [
        Country(c.alpha_2, translate(c.name), patterns.get(c.alpha_2)) for c in pycountry.countries
    ]
    return tuple(sorted(items, key=lambda c: _sort_key(c.name)))


@cache
def _countries_by_code() -> dict[str, Country]:
    return {c.code: c for c in countries()}


def find_country(code: str) -> Country | None:
    return _countries_by_code().get(code.strip().upper())


@cache
def provinces(country_code: str) -> tuple[Province, ...]:
    """The lowest-level ISO 3166-2 divisions of a country (for Spain: its provinces and
    the two autonomous cities), named in Spanish and sorted. Empty for countries without
    any."""
    country_code = country_code.strip().upper()
    translate = _translator("iso3166-2").gettext
    subdivisions = [s for s in pycountry.subdivisions if s.country_code == country_code]
    parents = {s.parent_code for s in subdivisions if s.parent_code}
    items = [
        Province(s.code, _clean(translate(s.name)), s.parent_code)
        for s in subdivisions
        if s.code not in parents
    ]
    return tuple(sorted(items, key=lambda p: _sort_key(p.name)))


def find_province(country_code: str, value: str) -> Province | None:
    """A province of the country by name (case- and accent-insensitive) or ISO code."""
    needle = _sort_key(value)
    for province in provinces(country_code):
        if needle in (_sort_key(province.name), province.code.casefold()):
            return province
    return None


def cities(country_code: str, province_code: str) -> tuple[str, ...]:
    """Known localities of a province: those keyed by the province itself, else by its
    parent division (GeoNames only records the autonomous community of Spanish
    localities), else none."""
    province = next((p for p in provinces(country_code) if p.code == province_code), None)
    if province is None:
        return ()
    data = _cities()
    found = data.get(province.code) or (data.get(province.parent_code or "") or [])
    return tuple(found)


def postal_code_matches(country_code: str, value: str) -> bool:
    """Whether `value` looks like a postal code of the country (always true for countries
    without a known pattern)."""
    pattern = _postal_code_patterns().get(country_code.strip().upper())
    return pattern is None or re.match(pattern, value.strip()) is not None


def _sort_key(name: str) -> str:
    """Case- and accent-insensitive form of a name (Álava sorts with Alava, not after Zamora)."""
    decomposed = unicodedata.normalize("NFD", name.strip().casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

"""Data fixtures: factory_boy factories shared by the test-suite and the `fixtures` CLI."""

from app.fixtures.factories import (
    FiscalDataFactory,
    InvoiceFactory,
    InvoiceLineFactory,
    IssuerFactory,
    SubjectFactory,
    UserFactory,
    bind_session,
    reseed,
)
from app.fixtures.loader import (
    DEMO_TENANT_EMAIL,
    DEMO_TENANT_PASSWORD,
    LoadReport,
    load_fixtures,
    purge_fixtures,
)

__all__ = [
    "DEMO_TENANT_EMAIL",
    "DEMO_TENANT_PASSWORD",
    "FiscalDataFactory",
    "InvoiceFactory",
    "InvoiceLineFactory",
    "IssuerFactory",
    "LoadReport",
    "SubjectFactory",
    "UserFactory",
    "bind_session",
    "load_fixtures",
    "purge_fixtures",
    "reseed",
]

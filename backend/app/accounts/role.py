from enum import StrEnum


class Role(StrEnum):
    """What a user can do in the system.

    SUPER_ADMIN -- manages the accounts (tenants) of the system; has no invoicing data.
    ADMIN       -- owner of a tenant: manages its own invoices, clients and settings.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"

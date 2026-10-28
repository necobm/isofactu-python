from enum import StrEnum


class InvoiceState(StrEnum):
    """Lifecycle state of an Invoice.

    DRAFT   -- being prepared; not yet delivered to the recipient.
    ISSUED  -- finalised and emitted.
    """

    DRAFT = "DRAFT"
    ISSUED = "ISSUED"

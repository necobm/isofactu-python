from enum import StrEnum


class PaymentMethod(StrEnum):
    """How an invoice is expected to be paid."""

    TRANSFER = "TRANSFER"
    CASH = "CASH"
    CARD = "CARD"
    DIRECT_DEBIT = "DIRECT_DEBIT"

from enum import StrEnum


class InvoiceKind(StrEnum):
    """Which book an Invoice belongs to (Spanish *libro de facturas emitidas / recibidas*).

    ISSUED    -- issued by the tenant to a client (income). The issuer is the tenant's
                 fiscal data; the number is taken from one of its serials.
    RECEIVED  -- received by the tenant from a supplier (expense). The issuer (supplier)
                 and the number are entered by hand; the recipient is the tenant's fiscal data.
                 No drafts: always stored as ISSUED (by the supplier) and always editable.
    """

    ISSUED = "ISSUED"
    RECEIVED = "RECEIVED"

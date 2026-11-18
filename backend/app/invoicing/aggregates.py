"""Invoice amounts computed in SQL, for reports that add up many invoices (dashboard, taxes).

Invoice amounts are not stored: the models compute them from the lines (`Invoice.subtotal`,
`.tax_amount`, `.retention_amount`, `.total`). The expressions below do exactly the same in
SQL -- per line ``base = round(quantity * unit_price, 2)`` and
``tax = round(base * round(rate / 100, 4), 2)``, per invoice
``retention = round(base * round(retention_rate / 100, 4), 2)`` -- and PostgreSQL's
``round(numeric)`` breaks ties away from zero like Python's ``ROUND_HALF_UP``, so the totals
match the invoices to the cent (``tests/test_dashboard.py`` and ``tests/test_taxes.py`` check
it).

Select from ``invoices_with_amounts`` (every invoice joined with its amounts) and use
``base``, ``tax``, ``retention`` and ``total`` as columns; ``invoice`` holds the invoice's own
columns. Reports only count final invoices (ISSUED; received invoices always are): drafts
are neither income nor VAT.
"""

from decimal import Decimal

from sqlalchemy import func, select

from app.invoicing.models import Invoice, InvoiceLine

ZERO = Decimal("0.00")

invoice = Invoice.__table__.c
_line = InvoiceLine.__table__.c

_line_base = func.round(_line.quantity * _line.unit_price, 2)
_line_tax = func.round(_line_base * func.round(_line.tax_rate / 100, 4), 2)
_per_invoice = (
    select(
        _line.invoice_id.label("invoice_id"),
        func.sum(_line_base).label("base"),
        func.sum(_line_tax).label("tax"),
    )
    .group_by(_line.invoice_id)
    .subquery("invoice_amounts")
)

# Amounts of one invoice, as columns of `invoices_with_amounts`
base = func.coalesce(_per_invoice.c.base, ZERO)
tax = func.coalesce(_per_invoice.c.tax, ZERO)
retention = func.round(base * func.round(invoice.retention_rate / 100, 4), 2)
total = base + tax - retention
invoices_with_amounts = Invoice.__table__.outerjoin(
    _per_invoice, _per_invoice.c.invoice_id == invoice.id
)


def sum_of(expression, *, where=None):
    """The sum of ``expression`` over the selected invoices (0 when there are none),
    optionally only over those matching ``where`` (an SQL ``FILTER``)."""
    total_ = func.sum(expression) if where is None else func.sum(expression).filter(where)
    return func.coalesce(total_, ZERO)

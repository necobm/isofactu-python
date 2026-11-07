"""Invoicing module: received invoices (expenses) share the invoice table with issued ones

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-15 00:00:00 UTC

Invoices gain a `kind`: ISSUED (income, the only kind so far) or RECEIVED (a supplier's
invoice, recorded as an expense). Received invoices store the supplier in the issuer
columns, a copy of the tenant's fiscal data as recipient and the supplier's number as
entered; they never take a number from a serial, which a check constraint enforces. Every
existing invoice is an issued one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoice",
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="ISSUED"),
    )
    # The default only back-fills existing rows; the application always sets the kind.
    op.alter_column("invoice", "kind", server_default=None)
    op.create_index(op.f("ix_invoice_kind"), "invoice", ["kind"])
    op.create_check_constraint(
        op.f("ck_invoice_serial_kind"), "invoice", "kind = 'ISSUED' OR serial_id IS NULL"
    )


def downgrade() -> None:
    # Without a kind, received invoices would pass for issued ones: drop them (their lines
    # go with them through the cascade) and then their recipient copies. Separate statements
    # on purpose: the parts of a single `WITH ... DELETE` all see the same snapshot.
    op.execute(
        "CREATE TEMPORARY TABLE received_recipient AS "
        "SELECT DISTINCT recipient_id AS id FROM invoice WHERE kind = 'RECEIVED'"
    )
    op.execute("DELETE FROM invoice WHERE kind = 'RECEIVED'")
    op.execute(
        "DELETE FROM subject WHERE id IN (SELECT id FROM received_recipient) "
        "AND NOT EXISTS (SELECT 1 FROM invoice WHERE invoice.recipient_id = subject.id)"
    )
    op.execute("DROP TABLE received_recipient")
    op.drop_constraint(op.f("ck_invoice_serial_kind"), "invoice", type_="check")
    op.drop_index(op.f("ix_invoice_kind"), table_name="invoice")
    op.drop_column("invoice", "kind")

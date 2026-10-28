"""Invoicing module: IRPF retention applies to the whole invoice, not per line

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-20 00:00:00 UTC

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "invoice",
        sa.Column(
            "retention_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"
        ),
    )
    # Carry over any per-line retention (the highest rate used on the invoice).
    op.execute(
        """
        UPDATE invoice SET retention_rate = lines.rate
        FROM (
            SELECT invoice_id, MAX(retention_rate) AS rate FROM invoice_line GROUP BY invoice_id
        ) AS lines
        WHERE lines.invoice_id = invoice.id
        """
    )
    op.alter_column("invoice", "retention_rate", server_default=None)
    op.drop_column("invoice_line", "retention_rate")


def downgrade() -> None:
    op.add_column(
        "invoice_line",
        sa.Column(
            "retention_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"
        ),
    )
    op.execute(
        """
        UPDATE invoice_line SET retention_rate = invoice.retention_rate
        FROM invoice WHERE invoice.id = invoice_line.invoice_id
        """
    )
    op.alter_column("invoice_line", "retention_rate", server_default=None)
    op.drop_column("invoice", "retention_rate")

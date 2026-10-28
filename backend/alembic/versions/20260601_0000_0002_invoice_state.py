"""Invoicing module: add invoice.state (DRAFT | ISSUED)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01 00:00:00 UTC

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Invoices stored before this revision were all "live" invoices, so they are backfilled
    # as ISSUED. The temporary server default only exists to populate existing rows; the
    # application always sends an explicit value (DRAFT by default for new invoices).
    op.add_column(
        "invoice",
        sa.Column("state", sa.String(length=10), nullable=False, server_default="ISSUED"),
    )
    op.alter_column("invoice", "state", server_default=None)
    op.create_index(op.f("ix_invoice_state"), "invoice", ["state"])


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_state"), table_name="invoice")
    op.drop_column("invoice", "state")

"""Invoicing module: numberless drafts, notes, due date, payment method, line retention

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15 00:00:00 UTC

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drafts have no number: the column becomes nullable and the (unassigned) empty
    # strings that the old API could store are normalised to NULL.
    op.alter_column("invoice", "number", existing_type=sa.String(length=100), nullable=True)
    op.execute("UPDATE invoice SET number = NULL WHERE number = ''")

    # Temporary server defaults only backfill existing rows; the application always sends
    # explicit values, so they are dropped right away to keep the schema equal to the model.
    op.add_column("invoice", sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    op.add_column("invoice", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column(
        "invoice",
        sa.Column(
            "payment_method", sa.String(length=20), nullable=False, server_default="TRANSFER"
        ),
    )
    op.alter_column("invoice", "notes", server_default=None)
    op.alter_column("invoice", "payment_method", server_default=None)

    op.add_column(
        "invoice_line",
        sa.Column(
            "retention_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"
        ),
    )
    op.alter_column("invoice_line", "retention_rate", server_default=None)


def downgrade() -> None:
    op.drop_column("invoice_line", "retention_rate")
    op.drop_column("invoice", "payment_method")
    op.drop_column("invoice", "due_date")
    op.drop_column("invoice", "notes")
    # Drafts have no number: give them an empty string before restoring NOT NULL.
    op.execute("UPDATE invoice SET number = '' WHERE number IS NULL")
    op.alter_column("invoice", "number", existing_type=sa.String(length=100), nullable=False)

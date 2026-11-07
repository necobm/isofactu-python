"""Invoicing module: issued invoices record when they were collected

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-15 00:00:00 UTC

Issued invoices gain `collected_on`, the day the client paid them (NULL while pending), so
that the dashboard can tell which invoices are still to be collected. Only final issued
invoices can be collected, never before their issue date. Existing invoices start pending.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invoice", sa.Column("collected_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        op.f("ck_invoice_collected_when_issued"),
        "invoice",
        "collected_on IS NULL OR (kind = 'ISSUED' AND state = 'ISSUED')",
    )
    op.create_check_constraint(
        op.f("ck_invoice_collected_after_issue"),
        "invoice",
        "collected_on IS NULL OR collected_on >= issue_date",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_invoice_collected_after_issue"), "invoice", type_="check")
    op.drop_constraint(op.f("ck_invoice_collected_when_issued"), "invoice", type_="check")
    op.drop_column("invoice", "collected_on")

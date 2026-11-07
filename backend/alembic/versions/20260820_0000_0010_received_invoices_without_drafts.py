"""Invoicing module: received invoices have no drafts

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-20 00:00:00 UTC

A received invoice was issued by its supplier before the tenant records it: it has no
DRAFT -> ISSUED lifecycle, is always stored as ISSUED and stays editable. Received drafts
recorded until now become plain received invoices (one still without a supplier number
shows none until it is edited, which requires it), and a check constraint keeps it so.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE invoice SET state = 'ISSUED' WHERE kind = 'RECEIVED' AND state <> 'ISSUED'")
    op.create_check_constraint(
        op.f("ck_invoice_received_state"), "invoice", "kind = 'ISSUED' OR state = 'ISSUED'"
    )


def downgrade() -> None:
    # Nothing to restore: which received invoices used to be drafts is not recorded.
    op.drop_constraint(op.f("ck_invoice_received_state"), "invoice", type_="check")

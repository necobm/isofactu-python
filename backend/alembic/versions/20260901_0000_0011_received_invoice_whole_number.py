"""Invoicing module: the number of a received invoice is one whole string

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-01 00:00:00 UTC

Received invoices used to store the supplier's number as a series (`number_prefix`) plus a
number. Which part of a supplier's number is its series is not something the user can
tell, so the number is now kept whole: existing prefixes / suffixes are folded into the
number (the rendered number does not change), and a check constraint keeps them empty.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE invoice SET number = number_prefix || number || number_suffix, "
        "number_prefix = '', number_suffix = '' "
        "WHERE kind = 'RECEIVED' AND number IS NOT NULL "
        "AND (number_prefix <> '' OR number_suffix <> '')"
    )
    op.create_check_constraint(
        op.f("ck_invoice_received_whole_number"),
        "invoice",
        "kind = 'ISSUED' OR (number_prefix = '' AND number_suffix = '')",
    )


def downgrade() -> None:
    # The whole number stays in `number`: it still renders the same.
    op.drop_constraint(op.f("ck_invoice_received_whole_number"), "invoice", type_="check")

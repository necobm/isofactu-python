"""Invoicing module: numbering serials per tenant; invoice numbers carry prefix and suffix

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-20 00:00:00 UTC

Invoice numbers used to be a free-text `serial` plus a number, rendered `serial-number`. They
are now taken from a managed `serial` entity (prefix + sequential number + suffix) and the
invoice stores a copy of the prefix / suffix. Every legacy serial string `X` becomes a serial
with prefix `X-` (so existing numbers render exactly as before), and the invoices that used
it are linked to it; invoices issued without a serial keep an empty prefix and no link.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "serial",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("prefix", sa.String(length=100), nullable=False),
        sa.Column("suffix", sa.String(length=100), nullable=False),
        sa.Column("initial_number", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.CheckConstraint("prefix <> '' OR suffix <> ''", name=op.f("ck_serial_prefix_or_suffix")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_serial")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user_account.id"],
            name=op.f("fk_serial_owner_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "owner_id", "prefix", "suffix", name=op.f("uq_serial_owner_id_prefix_suffix")
        ),
    )
    op.create_index(op.f("ix_serial_owner_id"), "serial", ["owner_id"])

    # -- the invoice number: (prefix, number, suffix) + link to the serial ---------------
    op.alter_column("invoice", "serial", new_column_name="number_prefix")
    op.execute(
        "UPDATE invoice SET number_prefix = CASE WHEN number_prefix IS NULL OR number_prefix = '' "
        "THEN '' ELSE number_prefix || '-' END"
    )
    op.alter_column("invoice", "number_prefix", nullable=False)
    op.add_column(
        "invoice",
        sa.Column("number_suffix", sa.String(length=100), nullable=False, server_default=""),
    )
    op.alter_column("invoice", "number_suffix", server_default=None)
    op.add_column("invoice", sa.Column("serial_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_invoice_serial_id_serial"), "invoice", "serial", ["serial_id"], ["id"]
    )
    op.create_index(op.f("ix_invoice_serial_id"), "invoice", ["serial_id"])

    # -- one serial per (tenant, legacy serial string), linked to its invoices ----------
    op.execute(
        """
        INSERT INTO serial (owner_id, prefix, suffix, initial_number)
        SELECT DISTINCT owner_id, number_prefix, '', 1
        FROM invoice WHERE number_prefix <> ''
        """
    )
    op.execute(
        """
        UPDATE invoice SET serial_id = s.id
        FROM serial AS s
        WHERE s.owner_id = invoice.owner_id AND s.prefix = invoice.number_prefix
          AND invoice.number_prefix <> ''
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_serial_id"), table_name="invoice")
    op.drop_constraint(op.f("fk_invoice_serial_id_serial"), "invoice", type_="foreignkey")
    op.drop_column("invoice", "serial_id")
    op.drop_column("invoice", "number_suffix")
    # Back to the free-text serial: drop the trailing separator added on upgrade.
    op.alter_column("invoice", "number_prefix", new_column_name="serial", nullable=True)
    op.execute(
        "UPDATE invoice SET serial = CASE WHEN serial = '' THEN NULL "
        "ELSE regexp_replace(serial, '-$', '') END"
    )
    op.drop_index(op.f("ix_serial_owner_id"), table_name="serial")
    op.drop_table("serial")

"""Invoicing module: initial schema (subject, invoice, invoice_line)

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00 UTC

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subject",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=10), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=False),
        sa.Column("address_street", sa.String(length=255), nullable=False),
        sa.Column("address_zip_code", sa.String(length=50), nullable=False),
        sa.Column("address_city", sa.String(length=100), nullable=False),
        sa.Column("address_province", sa.String(length=100), nullable=False),
        sa.Column("address_country_iso_code", sa.String(length=2), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject")),
    )
    op.create_index(op.f("ix_subject_document_number"), "subject", ["document_number"])

    op.create_table(
        "invoice",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("issuer_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("serial", sa.String(length=100), nullable=True),
        sa.Column("number", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice")),
        sa.ForeignKeyConstraint(
            ["issuer_id"], ["subject.id"], name=op.f("fk_invoice_issuer_id_subject")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["subject.id"], name=op.f("fk_invoice_recipient_id_subject")
        ),
    )
    op.create_index(op.f("ix_invoice_issuer_id"), "invoice", ["issuer_id"])
    op.create_index(op.f("ix_invoice_recipient_id"), "invoice", ["recipient_id"])
    op.create_index(op.f("ix_invoice_issue_date"), "invoice", ["issue_date"])

    op.create_table(
        "invoice_line",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_line")),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoice.id"],
            name=op.f("fk_invoice_line_invoice_id_invoice"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_invoice_line_invoice_id"), "invoice_line", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("invoice_line")
    op.drop_table("invoice")
    op.drop_table("subject")

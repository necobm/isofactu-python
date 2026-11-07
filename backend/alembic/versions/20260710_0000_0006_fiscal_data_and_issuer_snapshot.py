"""Invoicing module: fiscal data per tenant; invoices carry a copy of the issuer

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10 00:00:00 UTC

Before this revision an invoice pointed at a `subject` row as issuer. Now the issuer is a
snapshot stored on the invoice itself (so issued invoices are unaffected by later changes),
taken from the tenant's `fiscal_data` when the invoice is saved. Existing invoices get their
snapshot copied from the subject they referenced, and each tenant gets its fiscal data
seeded from the issuer of its most recent invoice, so nothing has to be re-entered.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISSUER_COLUMNS = (
    ("issuer_name", sa.String(length=255), "full_name"),
    ("issuer_document_type", sa.String(length=10), "document_type"),
    ("issuer_document_number", sa.String(length=100), "document_number"),
    ("issuer_address_street", sa.String(length=255), "address_street"),
    ("issuer_address_zip_code", sa.String(length=50), "address_zip_code"),
    ("issuer_address_city", sa.String(length=100), "address_city"),
    ("issuer_address_province", sa.String(length=100), "address_province"),
    ("issuer_address_country_iso_code", sa.String(length=2), "address_country_iso_code"),
)


def upgrade() -> None:
    op.create_table(
        "fiscal_data",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=10), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=False),
        sa.Column("address_street", sa.String(length=255), nullable=False),
        sa.Column("address_zip_code", sa.String(length=50), nullable=False),
        sa.Column("address_city", sa.String(length=100), nullable=False),
        sa.Column("address_province", sa.String(length=100), nullable=False),
        sa.Column("address_country_iso_code", sa.String(length=2), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fiscal_data")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user_account.id"],
            name=op.f("fk_fiscal_data_owner_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("owner_id", name=op.f("uq_fiscal_data_owner_id")),
    )

    # -- issuer snapshot on the invoice --------------------------------------------------
    for column, type_, _ in ISSUER_COLUMNS:
        op.add_column("invoice", sa.Column(column, type_, nullable=True))
    assignments = ", ".join(f"{column} = s.{source}" for column, _, source in ISSUER_COLUMNS)
    op.execute(f"UPDATE invoice SET {assignments} FROM subject AS s WHERE s.id = invoice.issuer_id")
    for column, _, _ in ISSUER_COLUMNS:
        op.alter_column("invoice", column, nullable=False)

    # -- seed each tenant's fiscal data from the issuer of its most recent invoice --------
    op.execute(
        """
        INSERT INTO fiscal_data (owner_id, company_name, document_type, document_number,
                                 address_street, address_zip_code, address_city,
                                 address_province, address_country_iso_code)
        SELECT DISTINCT ON (owner_id) owner_id, issuer_name, issuer_document_type,
               issuer_document_number, issuer_address_street, issuer_address_zip_code,
               issuer_address_city, issuer_address_province, issuer_address_country_iso_code
        FROM invoice
        ORDER BY owner_id, issue_date DESC, id DESC
        """
    )

    op.drop_index(op.f("ix_invoice_issuer_id"), table_name="invoice")
    op.drop_constraint(op.f("fk_invoice_issuer_id_subject"), "invoice", type_="foreignkey")
    op.drop_column("invoice", "issuer_id")


def downgrade() -> None:
    op.add_column("invoice", sa.Column("issuer_id", sa.Integer(), nullable=True))
    # Point each invoice at a subject matching its snapshot (same tenant, name and document),
    # creating the subject when there is none.
    op.execute(
        """
        INSERT INTO subject (owner_id, full_name, document_type, document_number, address_street,
                             address_zip_code, address_city, address_province,
                             address_country_iso_code)
        SELECT DISTINCT i.owner_id, i.issuer_name, i.issuer_document_type,
               i.issuer_document_number, i.issuer_address_street, i.issuer_address_zip_code,
               i.issuer_address_city, i.issuer_address_province,
               i.issuer_address_country_iso_code
        FROM invoice AS i
        WHERE NOT EXISTS (
            SELECT 1 FROM subject AS s
            WHERE s.owner_id = i.owner_id AND s.full_name = i.issuer_name
              AND s.document_number = i.issuer_document_number
        )
        """
    )
    op.execute(
        """
        UPDATE invoice SET issuer_id = (
            SELECT s.id FROM subject AS s
            WHERE s.owner_id = invoice.owner_id AND s.full_name = invoice.issuer_name
              AND s.document_number = invoice.issuer_document_number
            ORDER BY s.id LIMIT 1
        )
        """
    )
    op.alter_column("invoice", "issuer_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_invoice_issuer_id_subject"), "invoice", "subject", ["issuer_id"], ["id"]
    )
    op.create_index(op.f("ix_invoice_issuer_id"), "invoice", ["issuer_id"])
    for column, _, _ in ISSUER_COLUMNS:
        op.drop_column("invoice", column)
    op.drop_table("fiscal_data")

"""Clients module: the client directory; subjects become the invoices' own recipient copies

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-01 00:00:00 UTC

Clients used to be `subject` rows picked directly as invoice recipients. They now live in
their own `client` table and an invoice gets its *own copy* of the chosen client as its
`subject`, so editing or deleting a client never affects an invoice. Every existing subject
is copied into the client directory; subjects no invoice refers to are then dropped (they
were only ever client entries), while the ones invoices point at stay as their recipients.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIELDS = (
    "owner_id, full_name, document_type, document_number, address_street, address_zip_code, "
    "address_city, address_province, address_country_iso_code"
)


def upgrade() -> None:
    op.create_table(
        "client",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=10), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=False),
        sa.Column("address_street", sa.String(length=255), nullable=False),
        sa.Column("address_zip_code", sa.String(length=50), nullable=False),
        sa.Column("address_city", sa.String(length=100), nullable=False),
        sa.Column("address_province", sa.String(length=100), nullable=False),
        sa.Column("address_country_iso_code", sa.String(length=2), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user_account.id"],
            name=op.f("fk_client_owner_id_user_account"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_client_owner_id"), "client", ["owner_id"])
    op.create_index(op.f("ix_client_document_number"), "client", ["document_number"])

    op.execute(f"INSERT INTO client ({FIELDS}) SELECT {FIELDS} FROM subject ORDER BY id")
    op.execute(
        "DELETE FROM subject WHERE NOT EXISTS "
        "(SELECT 1 FROM invoice WHERE invoice.recipient_id = subject.id)"
    )


def downgrade() -> None:
    # Clients that no invoice copy matches become subjects again (same tenant, name and
    # document); the rest are already present as recipients.
    op.execute(
        f"""
        INSERT INTO subject ({FIELDS})
        SELECT {FIELDS} FROM client AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM subject AS s
            WHERE s.owner_id = c.owner_id AND s.full_name = c.full_name
              AND s.document_number = c.document_number
        )
        ORDER BY c.id
        """
    )
    op.drop_index(op.f("ix_client_document_number"), table_name="client")
    op.drop_index(op.f("ix_client_owner_id"), table_name="client")
    op.drop_table("client")

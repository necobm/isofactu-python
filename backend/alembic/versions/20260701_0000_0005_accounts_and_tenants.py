"""Accounts module: users, activation links, system settings; subjects and invoices get an owner

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-01 00:00:00 UTC

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Rows created before accounts existed (single-tenant era) are handed to this paused
# account so that nothing is lost. A SUPER_ADMIN can rename it, send it an activation
# link, or delete it (which removes the legacy data) from the admin panel.
LEGACY_TENANT_EMAIL = "legacy@isofactu.local"


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_account")),
        sa.UniqueConstraint("email", name=op.f("uq_user_account_email")),
    )

    op.create_table(
        "activation_token",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activation_token")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name=op.f("fk_activation_token_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name=op.f("uq_activation_token_user_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_activation_token_token_hash")),
    )

    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
    )

    # -- tenant ownership of the invoicing data ------------------------------------------
    op.add_column("subject", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("invoice", sa.Column("owner_id", sa.Integer(), nullable=True))

    connection = op.get_bind()
    orphans = connection.execute(
        sa.text("SELECT (SELECT count(*) FROM subject) + (SELECT count(*) FROM invoice)")
    ).scalar_one()
    if orphans:
        legacy_id = connection.execute(
            sa.text(
                "INSERT INTO user_account (email, role, status, name, created_at) "
                "VALUES (:email, 'ADMIN', 'PAUSED', 'Datos anteriores a las cuentas', :now) "
                "RETURNING id"
            ),
            {"email": LEGACY_TENANT_EMAIL, "now": datetime.now(UTC)},
        ).scalar_one()
        for table in ("subject", "invoice"):
            connection.execute(
                sa.text(f"UPDATE {table} SET owner_id = :owner"), {"owner": legacy_id}
            )

    for table in ("subject", "invoice"):
        op.alter_column(table, "owner_id", nullable=False)
        op.create_foreign_key(
            op.f(f"fk_{table}_owner_id_user_account"),
            table,
            "user_account",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(op.f(f"ix_{table}_owner_id"), table, ["owner_id"])


def downgrade() -> None:
    for table in ("invoice", "subject"):
        op.drop_index(op.f(f"ix_{table}_owner_id"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_owner_id_user_account"), table, type_="foreignkey")
        op.drop_column(table, "owner_id")
    op.drop_table("app_setting")
    op.drop_table("activation_token")
    op.drop_table("user_account")

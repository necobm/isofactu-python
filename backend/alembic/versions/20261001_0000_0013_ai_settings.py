"""AI module: each tenant's AI vendor for reading received invoices

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01 00:00:00 UTC

PDF import used to read its vendor, model and API key from the server environment
(`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`), shared by every tenant. Each
tenant now sets its own in `ai_settings` (at most one row per account), with the API key
encrypted (see `app.core.crypto`). Nothing is migrated: the environment values are no longer
read, so tenants set up their own vendor in the settings.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("api_version", sa.String(length=50), nullable=False),
        sa.Column("deployment", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_settings")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user_account.id"],
            name=op.f("fk_ai_settings_owner_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("owner_id", name=op.f("uq_ai_settings_owner_id")),
    )


def downgrade() -> None:
    op.drop_table("ai_settings")

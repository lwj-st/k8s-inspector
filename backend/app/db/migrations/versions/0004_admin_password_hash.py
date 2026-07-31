"""Persist the administrator password hash in system settings."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "admin_password_hash"
down_revision: str | Sequence[str] | None = "system_cluster_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("system_settings")}
    if "admin_password_hash" not in existing_columns:
        op.add_column(
            "system_settings",
            sa.Column("admin_password_hash", sa.String(512), nullable=True),
        )
    configured_hash = context_admin_password_hash()
    if configured_hash:
        bind.execute(
            sa.text(
                "UPDATE system_settings "
                "SET admin_password_hash = :admin_password_hash "
                "WHERE id = 1 AND (admin_password_hash IS NULL OR admin_password_hash = '')"
            ),
            {"admin_password_hash": configured_hash},
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("system_settings")}
    if "admin_password_hash" in existing_columns:
        with op.batch_alter_table("system_settings") as batch:
            batch.drop_column("admin_password_hash")


def context_admin_password_hash() -> str | None:
    import os

    configured = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    return configured or None

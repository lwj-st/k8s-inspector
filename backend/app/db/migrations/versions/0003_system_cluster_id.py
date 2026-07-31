"""Persist the runtime cluster identifier in system settings."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "system_cluster_id"
down_revision: str | Sequence[str] | None = "v110_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("system_settings")}
    if "cluster_id" not in existing_columns:
        op.add_column(
            "system_settings",
            sa.Column(
                "cluster_id",
                sa.String(128),
                nullable=False,
                server_default="local",
            ),
        )
    configured_cluster_id = context_cluster_id(bind)
    bind.execute(
        sa.text(
            "UPDATE system_settings "
            "SET cluster_id = :cluster_id "
            "WHERE id = 1 AND (cluster_id IS NULL OR cluster_id = '' OR cluster_id = 'local')"
        ),
        {"cluster_id": configured_cluster_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("system_settings")}
    if "cluster_id" in existing_columns:
        with op.batch_alter_table("system_settings") as batch:
            batch.drop_column("cluster_id")


def context_cluster_id(bind) -> str:
    # Alembic does not own application settings; read the same process env used by
    # app.core.config without importing the whole application stack.
    import os

    configured = os.getenv("CLUSTER_ID", "").strip()
    return configured or "local"

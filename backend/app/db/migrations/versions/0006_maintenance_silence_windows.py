"""Add maintenance silence windows for notification suppression."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "maintenance_silence_windows"
down_revision: str | Sequence[str] | None = "issue_event_actor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_silence_windows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("namespace", sa.String(253), nullable=True),
        sa.Column("resource_kind", sa.String(128), nullable=True),
        sa.Column("label_selector", sa.String(512), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("pending_summary_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_maintenance_silence_enabled_time",
        "maintenance_silence_windows",
        ["enabled", "start_at", "end_at"],
    )
    op.create_index(
        "ix_maintenance_silence_scope_type",
        "maintenance_silence_windows",
        ["scope_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_silence_scope_type", table_name="maintenance_silence_windows")
    op.drop_index("ix_maintenance_silence_enabled_time", table_name="maintenance_silence_windows")
    op.drop_table("maintenance_silence_windows")

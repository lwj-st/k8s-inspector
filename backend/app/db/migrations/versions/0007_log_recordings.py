"""Add v1.3 log recording persistence tables."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "log_recordings"
down_revision: str | Sequence[str] | None = "maintenance_silence_windows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "log_recordings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("namespace", sa.String(253), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_source", sa.String(32), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String(64), nullable=True),
        sa.Column("pod_count", sa.Integer(), nullable=False),
        sa.Column("container_count", sa.Integer(), nullable=False),
        sa.Column("raw_line_count", sa.Integer(), nullable=False),
        sa.Column("folded_line_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_log_recordings_namespace_status_started",
        "log_recordings",
        ["namespace", "status", "started_at"],
    )
    op.create_index(
        "ix_log_recordings_status_planned_end",
        "log_recordings",
        ["status", "planned_end_at"],
    )

    op.create_table(
        "log_recording_pods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(253), nullable=False),
        sa.Column("pod_uid", sa.String(128), nullable=False),
        sa.Column("pod_name", sa.String(253), nullable=False),
        sa.Column("node_name", sa.String(253), nullable=True),
        sa.Column("owner_kind", sa.String(128), nullable=True),
        sa.Column("owner_name", sa.String(253), nullable=True),
        sa.Column("container_count", sa.Integer(), nullable=False),
        sa.Column("raw_line_count", sa.Integer(), nullable=False),
        sa.Column("folded_line_count", sa.Integer(), nullable=False),
        sa.Column("keyword_hit_count", sa.Integer(), nullable=False),
        sa.Column("deleted_during_recording", sa.Boolean(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("collection_error", sa.String(1000), nullable=True),
        sa.UniqueConstraint("recording_id", "pod_uid", name="uq_log_recording_pods_recording_uid"),
    )
    op.create_index(
        "ix_log_recording_pods_recording_pod",
        "log_recording_pods",
        ["recording_id", "pod_name"],
    )
    op.create_index(
        "ix_log_recording_pods_recording_hits",
        "log_recording_pods",
        ["recording_id", "keyword_hit_count"],
    )

    op.create_table(
        "log_recording_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pod_uid", sa.String(128), nullable=True),
        sa.Column("pod_name", sa.String(253), nullable=False),
        sa.Column("container_name", sa.String(253), nullable=False),
        sa.Column("log_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("line_text", sa.Text(), nullable=False),
        sa.Column("normalized_fingerprint", sa.String(64), nullable=False),
        sa.Column("repeat_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redacted", sa.Boolean(), nullable=False),
        sa.Column("folded", sa.Boolean(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_log_recording_lines_recording_pod_container",
        "log_recording_lines",
        ["recording_id", "pod_name", "container_name"],
    )
    op.create_index(
        "ix_log_recording_lines_recording_log_time",
        "log_recording_lines",
        ["recording_id", "log_time"],
    )
    op.create_index(
        "ix_log_recording_lines_recording_fingerprint",
        "log_recording_lines",
        ["recording_id", "normalized_fingerprint"],
    )

    op.create_table(
        "log_recording_template_matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recording_id", sa.Integer(), sa.ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("fault_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_name", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("pod_name", sa.String(253), nullable=False),
        sa.Column("container_name", sa.String(253), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("matched_context", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_log_recording_template_matches_recording",
        "log_recording_template_matches",
        ["recording_id", "severity"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_recording_template_matches_recording", table_name="log_recording_template_matches")
    op.drop_table("log_recording_template_matches")
    op.drop_index("ix_log_recording_lines_recording_fingerprint", table_name="log_recording_lines")
    op.drop_index("ix_log_recording_lines_recording_log_time", table_name="log_recording_lines")
    op.drop_index("ix_log_recording_lines_recording_pod_container", table_name="log_recording_lines")
    op.drop_table("log_recording_lines")
    op.drop_index("ix_log_recording_pods_recording_hits", table_name="log_recording_pods")
    op.drop_index("ix_log_recording_pods_recording_pod", table_name="log_recording_pods")
    op.drop_table("log_recording_pods")
    op.drop_index("ix_log_recordings_status_planned_end", table_name="log_recordings")
    op.drop_index("ix_log_recordings_namespace_status_started", table_name="log_recordings")
    op.drop_table("log_recordings")

"""Create the v1.0.0 baseline schema for a new database."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "v100_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("direction", sa.String(128), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("matched_templates", sa.JSON(), nullable=False),
        sa.Column("evidence_summary", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("llm_result", sa.JSON()),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "fault_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scenario", sa.String(64), nullable=False),
        sa.Column("target_groups", sa.JSON(), nullable=False),
        sa.Column("object_scope", sa.String(255)),
        sa.Column("namespace_scope", sa.String(255)),
        sa.Column("label_selector", sa.String(255)),
        sa.Column("match_conditions", sa.JSON(), nullable=False),
        sa.Column("joint_rule", sa.JSON()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("command", sa.Text()),
        sa.Column("risk_note", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "inspection_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("inspection_type", sa.String(64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("summary_status", sa.String(64), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "keyword_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "saved_inspection_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("label_selector", sa.String(255)),
        sa.Column("pod_name", sa.String(255)),
        sa.Column("resource_scope", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_path", sa.String(128)),
        sa.Column("provider_mode", sa.String(32)),
        sa.Column("kubeconfig_path", sa.String(512)),
        sa.Column("kube_context", sa.String(255)),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_provider", sa.String(64)),
        sa.Column("model_endpoint", sa.String(255)),
        sa.Column("api_key", sa.String(255)),
        sa.Column("default_inspection_strategy", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "whitelists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("label_selector", sa.String(255)),
        sa.Column("pod_name_pattern", sa.String(255)),
        sa.Column("container_name", sa.String(255)),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for table_name in (
        "whitelists",
        "system_settings",
        "saved_inspection_targets",
        "keyword_rules",
        "inspection_records",
        "fault_templates",
        "diagnosis_records",
    ):
        op.drop_table(table_name)

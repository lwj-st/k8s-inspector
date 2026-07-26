"""Add v1.1 platform entities and encrypt the legacy LLM API key."""

from typing import Sequence

from alembic import context, op
import sqlalchemy as sa

from app.security.crypto import SensitiveValueCipher


revision: str = "v110_platform"
down_revision: str | Sequence[str] | None = "v100_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TABLES = (
    "inspection_plans",
    "inspection_runs",
    "inspection_check_results",
    "issues",
    "issue_scope_memberships",
    "issue_events",
    "notification_channels",
    "notification_deliveries",
    "resource_metric_states",
    "security_audit_logs",
    "admin_sessions",
    "inspection_plan_channels",
    "inspection_run_issues",
)


def _build_v110_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table("inspection_records", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    plans = sa.Table(
        "inspection_plans",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("normalized_name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("include_template_matching", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_status", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("normalized_name", name="uq_inspection_plans_normalized_name"),
    )
    sa.Index("ix_inspection_plans_enabled_next_run", plans.c.enabled, plans.c.next_run_at)
    runs = sa.Table(
        "inspection_runs",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.ForeignKey("inspection_plans.id", ondelete="SET NULL")),
        sa.Column("inspection_record_id", sa.ForeignKey("inspection_records.id", ondelete="SET NULL")),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("opened_issue_count", sa.Integer(), nullable=False),
        sa.Column("recovered_issue_count", sa.Integer(), nullable=False),
        sa.Column("kubernetes_api_calls", sa.Integer(), nullable=False),
        sa.Column("log_pods_read", sa.Integer(), nullable=False),
        sa.Column("collected_log_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("inspection_record_id", name="uq_inspection_runs_inspection_record"),
    )
    sa.Index("ix_inspection_runs_started_status_plan", runs.c.started_at, runs.c.status, runs.c.plan_id)
    sa.Table(
        "inspection_check_results",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(2000)),
        sa.Column("checked_objects", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "check_code",
            "scope_key",
            name="uq_inspection_check_results_run_check_scope",
        ),
    )
    issues = sa.Table(
        "issues",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cluster_id", sa.String(128), nullable=False),
        sa.Column("issue_code", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("resource_api_version", sa.String(128)),
        sa.Column("resource_kind", sa.String(128), nullable=False),
        sa.Column("resource_namespace", sa.String(253)),
        sa.Column("resource_name", sa.String(253), nullable=False),
        sa.Column("resource_uid", sa.String(128)),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("source_check", sa.String(128), nullable=False),
        sa.Column("correlation_key", sa.String(256)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledge_note", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cluster_id", "fingerprint", name="uq_issues_cluster_fingerprint"),
    )
    sa.Index("ix_issues_status_severity_last_seen", issues.c.status, issues.c.severity, issues.c.last_seen_at)
    sa.Index("ix_issues_resource_namespace", issues.c.resource_namespace)
    sa.Index("ix_issues_resource_kind", issues.c.resource_kind)
    sa.Index("ix_issues_source_check", issues.c.source_check)
    memberships = sa.Table(
        "issue_scope_memberships",
        metadata,
        sa.Column(
            "issue_id",
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_seen_run_id",
            sa.ForeignKey("inspection_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(active AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_at IS NOT NULL)",
            name="ck_issue_scope_memberships_active_deactivated",
        ),
    )
    sa.Index(
        "ix_issue_scope_memberships_scope_active",
        memberships.c.scope_key,
        memberships.c.active,
    )
    events = sa.Table(
        "issue_events",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.ForeignKey("issues.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.ForeignKey("inspection_runs.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("previous_status", sa.String(16)),
        sa.Column("new_status", sa.String(16)),
        sa.Column("previous_severity", sa.String(16)),
        sa.Column("new_severity", sa.String(16)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("evidence_codes", sa.JSON(), nullable=False),
    )
    sa.Index("ix_issue_events_issue_occurred", events.c.issue_id, events.c.occurred_at)
    channels = sa.Table(
        "notification_channels",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("normalized_name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("encrypted_webhook_url", sa.Text(), nullable=False),
        sa.Column("encrypted_signing_secret", sa.Text()),
        sa.Column("endpoint_masked", sa.String(512), nullable=False),
        sa.Column("mention_all_on_critical", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("normalized_name", name="uq_notification_channels_normalized_name"),
    )
    deliveries = sa.Table(
        "notification_deliveries",
        metadata,
        sa.Column(
            "channel_id",
            sa.ForeignKey("notification_channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deduplication_key", sa.String(256), nullable=False),
        sa.Column("issue_event_id", sa.ForeignKey("issue_events.id", ondelete="SET NULL")),
        sa.Column("run_id", sa.ForeignKey("inspection_runs.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("provider_code", sa.String(128)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("deduplication_key", name="uq_notification_deliveries_deduplication_key"),
    )
    sa.Index(
        "ix_notification_deliveries_status_retry_created",
        deliveries.c.status,
        deliveries.c.next_retry_at,
        deliveries.c.created_at,
    )
    sa.Table(
        "resource_metric_states",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cluster_id", sa.String(128), nullable=False),
        sa.Column("api_version", sa.String(128)),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("namespace", sa.String(253), nullable=False),
        sa.Column("name", sa.String(253), nullable=False),
        sa.Column("container_name", sa.String(253), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_millicores", sa.Integer()),
        sa.Column("memory_bytes", sa.Integer()),
        sa.Column("cpu_request_millicores", sa.Integer()),
        sa.Column("memory_request_bytes", sa.Integer()),
        sa.Column("cpu_limit_millicores", sa.Integer()),
        sa.Column("memory_limit_bytes", sa.Integer()),
        sa.Column("consecutive_cpu_over_threshold", sa.Integer(), nullable=False),
        sa.Column("consecutive_memory_over_threshold", sa.Integer(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "cluster_id",
            "kind",
            "namespace",
            "name",
            "container_name",
            name="uq_resource_metric_states_identity",
        ),
    )
    audits = sa.Table(
        "security_audit_logs",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128)),
        sa.Column("source_ip", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    sa.Index(
        "ix_security_audit_logs_occurred_action_outcome",
        audits.c.occurred_at,
        audits.c.action,
        audits.c.outcome,
    )
    sessions = sa.Table(
        "admin_sessions",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("csrf_token", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("source_ip", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    sa.Index(
        "ix_admin_sessions_revoked_expires",
        sessions.c.revoked_at,
        sessions.c.absolute_expires_at,
    )
    sa.Table(
        "inspection_plan_channels",
        metadata,
        sa.Column(
            "plan_id",
            sa.ForeignKey("inspection_plans.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "channel_id",
            sa.ForeignKey("notification_channels.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    sa.Table(
        "inspection_run_issues",
        metadata,
        sa.Column(
            "run_id",
            sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "issue_id",
            sa.ForeignKey("issues.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    return metadata


V110_METADATA = _build_v110_metadata()


def _cipher() -> SensitiveValueCipher:
    return SensitiveValueCipher.from_key(context.config.attributes.get("encryption_key"))


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("system_settings")}
    if "api_key_encrypted" not in existing_columns:
        op.add_column(
            "system_settings",
            sa.Column("api_key_encrypted", sa.String(4096), nullable=True),
        )
    if "inspection_policy" not in existing_columns:
        op.add_column(
            "system_settings",
            sa.Column(
                "inspection_policy",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )

    rows = bind.execute(sa.text("SELECT id, api_key FROM system_settings WHERE api_key IS NOT NULL"))
    plaintext_rows = [(row.id, row.api_key) for row in rows if row.api_key]
    if plaintext_rows:
        cipher = _cipher()
        for setting_id, api_key in plaintext_rows:
            encrypted = cipher.encrypt(api_key, purpose="llm_api_key")
            bind.execute(
                sa.text(
                    "UPDATE system_settings "
                    "SET api_key_encrypted = :encrypted, api_key = NULL WHERE id = :setting_id"
                ),
                {"encrypted": encrypted, "setting_id": setting_id},
            )

    V110_METADATA.create_all(
        bind=bind,
        tables=[V110_METADATA.tables[name] for name in _NEW_TABLES],
        checkfirst=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, api_key_encrypted FROM system_settings "
            "WHERE api_key_encrypted IS NOT NULL"
        )
    )
    encrypted_rows = [(row.id, row.api_key_encrypted) for row in rows if row.api_key_encrypted]
    if encrypted_rows:
        cipher = _cipher()
        for setting_id, encrypted in encrypted_rows:
            plaintext = cipher.decrypt(encrypted, purpose="llm_api_key")
            bind.execute(
                sa.text("UPDATE system_settings SET api_key = :value WHERE id = :setting_id"),
                {"value": plaintext, "setting_id": setting_id},
            )

    for table_name in reversed(_NEW_TABLES):
        V110_METADATA.tables[table_name].drop(bind=bind, checkfirst=True)

    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("inspection_policy")
        batch.drop_column("api_key_encrypted")

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


inspection_plan_channels = Table(
    "inspection_plan_channels",
    Base.metadata,
    Column("plan_id", ForeignKey("inspection_plans.id", ondelete="CASCADE"), primary_key=True),
    Column("channel_id", ForeignKey("notification_channels.id", ondelete="RESTRICT"), primary_key=True),
)


inspection_run_issues = Table(
    "inspection_run_issues",
    Base.metadata,
    Column("run_id", ForeignKey("inspection_runs.id", ondelete="CASCADE"), primary_key=True),
    Column("issue_id", ForeignKey("issues.id", ondelete="RESTRICT"), primary_key=True),
)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("cluster_id", "fingerprint", name="uq_issues_cluster_fingerprint"),
        Index("ix_issues_status_severity_last_seen", "status", "severity", "last_seen_at"),
        Index("ix_issues_resource_namespace", "resource_namespace"),
        Index("ix_issues_resource_kind", "resource_kind"),
        Index("ix_issues_source_check", "source_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(String(128), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_api_version: Mapped[str | None] = mapped_column(String(128))
    resource_kind: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_namespace: Mapped[str | None] = mapped_column(String(253))
    resource_name: Mapped[str] = mapped_column(String(253), nullable=False)
    resource_uid: Mapped[str | None] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_check: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_key: Mapped[str | None] = mapped_column(String(256))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledge_note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class IssueScopeMembership(Base):
    __tablename__ = "issue_scope_memberships"
    __table_args__ = (
        CheckConstraint(
            "(active AND deactivated_at IS NULL) OR "
            "(NOT active AND deactivated_at IS NOT NULL)",
            name="ck_issue_scope_memberships_active_deactivated",
        ),
        Index("ix_issue_scope_memberships_scope_active", "scope_key", "active"),
    )

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    last_seen_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspection_runs.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IssueEvent(Base):
    __tablename__ = "issue_events"
    __table_args__ = (Index("ix_issue_events_issue_occurred", "issue_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_runs.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(16))
    new_status: Mapped[str | None] = mapped_column(String(16))
    previous_severity: Mapped[str | None] = mapped_column(String(16))
    new_severity: Mapped[str | None] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    evidence_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class InspectionPlan(Base):
    __tablename__ = "inspection_plans"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_inspection_plans_normalized_name"),
        Index("ix_inspection_plans_enabled_next_run", "enabled", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False)
    include_template_matching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class InspectionRun(Base):
    __tablename__ = "inspection_runs"
    __table_args__ = (
        UniqueConstraint("inspection_record_id", name="uq_inspection_runs_inspection_record"),
        Index("ix_inspection_runs_started_status_plan", "started_at", "status", "plan_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_plans.id", ondelete="SET NULL"))
    inspection_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspection_records.id", ondelete="SET NULL")
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    opened_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovered_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kubernetes_api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    log_pods_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_log_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class InspectionCheckResult(Base):
    __tablename__ = "inspection_check_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "check_code",
            "scope_key",
            name="uq_inspection_check_results_run_check_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_runs.id", ondelete="CASCADE"), nullable=False
    )
    check_code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2000))
    checked_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scope: Mapped[dict] = mapped_column(JSON, nullable=False)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_notification_channels_normalized_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    encrypted_webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_signing_secret: Mapped[str | None] = mapped_column(Text)
    endpoint_masked: Mapped[str] = mapped_column(String(512), nullable=False)
    mention_all_on_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_notification_deliveries_deduplication_key"),
        Index("ix_notification_deliveries_status_retry_created", "status", "next_retry_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deduplication_key: Mapped[str] = mapped_column(String(256), nullable=False)
    issue_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("issue_events.id", ondelete="SET NULL")
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_runs.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_status: Mapped[int | None] = mapped_column(Integer)
    provider_code: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ResourceMetricState(Base):
    __tablename__ = "resource_metric_states"
    __table_args__ = (
        UniqueConstraint(
            "cluster_id",
            "kind",
            "namespace",
            "name",
            "container_name",
            name="uq_resource_metric_states_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(String(128), nullable=False)
    api_version: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(253), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(253), nullable=False)
    container_name: Mapped[str] = mapped_column(String(253), nullable=False, default="")
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cpu_millicores: Mapped[int | None] = mapped_column(Integer)
    memory_bytes: Mapped[int | None] = mapped_column(Integer)
    cpu_request_millicores: Mapped[int | None] = mapped_column(Integer)
    memory_request_bytes: Mapped[int | None] = mapped_column(Integer)
    cpu_limit_millicores: Mapped[int | None] = mapped_column(Integer)
    memory_limit_bytes: Mapped[int | None] = mapped_column(Integer)
    consecutive_cpu_over_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_memory_over_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"
    __table_args__ = (Index("ix_security_audit_logs_occurred_action_outcome", "occurred_at", "action", "outcome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    request_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
        Index("ix_admin_sessions_revoked_expires", "revoked_at", "absolute_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))


__all__ = [
    "AdminSession",
    "InspectionCheckResult",
    "InspectionPlan",
    "InspectionRun",
    "Issue",
    "IssueEvent",
    "IssueScopeMembership",
    "NotificationChannel",
    "NotificationDelivery",
    "ResourceMetricState",
    "SecurityAuditLog",
    "inspection_plan_channels",
    "inspection_run_issues",
]

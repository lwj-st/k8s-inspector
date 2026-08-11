from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LogRecording(Base):
    __tablename__ = "log_recordings"
    __table_args__ = (
        Index("ix_log_recordings_namespace_status_started", "namespace", "status", "started_at"),
        Index("ix_log_recordings_status_planned_end", "status", "planned_end_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(253), nullable=False)
    namespaces: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_source: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    pod_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    container_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folded_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class LogRecordingPod(Base):
    __tablename__ = "log_recording_pods"
    __table_args__ = (
        UniqueConstraint("recording_id", "pod_uid", name="uq_log_recording_pods_recording_uid"),
        Index("ix_log_recording_pods_recording_pod", "recording_id", "pod_name"),
        Index("ix_log_recording_pods_recording_hits", "recording_id", "keyword_hit_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False)
    namespace: Mapped[str] = mapped_column(String(253), nullable=False)
    pod_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    pod_name: Mapped[str] = mapped_column(String(253), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(253))
    owner_kind: Mapped[str | None] = mapped_column(String(128))
    owner_name: Mapped[str | None] = mapped_column(String(253))
    container_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folded_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    keyword_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_during_recording: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    collection_error: Mapped[str | None] = mapped_column(String(1000))


class LogRecordingLine(Base):
    __tablename__ = "log_recording_lines"
    __table_args__ = (
        Index("ix_log_recording_lines_recording_pod_container", "recording_id", "pod_name", "container_name"),
        Index("ix_log_recording_lines_recording_log_time", "recording_id", "log_time"),
        Index("ix_log_recording_lines_recording_fingerprint", "recording_id", "normalized_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False)
    pod_uid: Mapped[str | None] = mapped_column(String(128))
    pod_name: Mapped[str] = mapped_column(String(253), nullable=False)
    container_name: Mapped[str] = mapped_column(String(253), nullable=False)
    log_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    line_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    folded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LogRecordingTemplateMatch(Base):
    __tablename__ = "log_recording_template_matches"
    __table_args__ = (
        Index("ix_log_recording_template_matches_recording", "recording_id", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recording_id: Mapped[int] = mapped_column(ForeignKey("log_recordings.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("fault_templates.id", ondelete="SET NULL"))
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    pod_name: Mapped[str] = mapped_column(String(253), nullable=False)
    container_name: Mapped[str] = mapped_column(String(253), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    matched_context: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

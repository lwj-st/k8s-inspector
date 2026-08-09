from datetime import datetime, timezone
from enum import Enum

from pydantic import Field, field_validator, model_validator

from app.schemas.v1_1 import ContractModel


class LogRecordingContract(ContractModel):
    @field_validator("*", mode="before")
    @classmethod
    def assume_utc_for_database_datetimes(cls, value: object) -> object:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            return value.replace(tzinfo=timezone.utc)
        return value


class LogRecordingStatus(str, Enum):
    recording = "recording"
    completed = "completed"
    auto_completed = "auto_completed"
    failed = "failed"


class LogRecordingDurationSource(str, Enum):
    system_default = "system_default"
    preset = "preset"
    custom = "custom"


class LogRecordingStopReason(str, Enum):
    user_stopped = "user_stopped"
    system_default_timeout = "system_default_timeout"
    selected_duration_timeout = "selected_duration_timeout"
    max_recording_bytes_reached = "max_recording_bytes_reached"
    collection_failed = "collection_failed"
    recovery_failed_after_restart = "recovery_failed_after_restart"


class LogRecordingViewMode(str, Enum):
    folded = "folded"
    raw = "raw"


class LogRecordingBase(LogRecordingContract):
    name: str = Field(min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=253)
    note: str | None = Field(default=None, max_length=1000)


class LogRecordingCreate(LogRecordingBase):
    duration_source: LogRecordingDurationSource = LogRecordingDurationSource.system_default
    duration_minutes: int | None = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def require_duration_for_non_default(self) -> "LogRecordingCreate":
        if self.duration_source != LogRecordingDurationSource.system_default and self.duration_minutes is None:
            raise ValueError("duration_minutes is required when duration_source is not system_default")
        return self


class LogRecordingPreviewRequest(LogRecordingContract):
    namespace: str = Field(min_length=1, max_length=253)


class LogRecordingPreview(LogRecordingContract):
    namespace: str
    pod_count: int = Field(ge=0)
    container_count: int = Field(ge=0)
    allowed: bool
    reason: str | None = None


class LogRecordingStorageUsage(LogRecordingContract):
    used_bytes: int = Field(ge=0)
    max_bytes: int = Field(ge=1)
    used_percent: float = Field(ge=0)
    warning_threshold_percent: int = Field(ge=1, le=100)
    warning: bool
    full: bool


class LogRecordingUpdate(LogRecordingContract):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=1000)


class LogRecordingRead(LogRecordingBase):
    id: int
    status: LogRecordingStatus
    started_at: datetime
    ended_at: datetime | None = None
    planned_end_at: datetime
    duration_source: LogRecordingDurationSource
    duration_minutes: int = Field(ge=1)
    stop_reason: LogRecordingStopReason | None = None
    pod_count: int = Field(ge=0)
    container_count: int = Field(ge=0)
    raw_line_count: int = Field(ge=0)
    folded_line_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    truncated: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class LogRecordingPodRead(LogRecordingContract):
    id: int
    recording_id: int
    namespace: str
    pod_uid: str
    pod_name: str
    node_name: str | None = None
    owner_kind: str | None = None
    owner_name: str | None = None
    container_count: int = Field(ge=0)
    raw_line_count: int = Field(ge=0)
    folded_line_count: int = Field(ge=0)
    keyword_hit_count: int = Field(ge=0)
    deleted_during_recording: bool
    truncated: bool
    collection_error: str | None = None
    container_names: list[str] = Field(default_factory=list)


class LogRecordingLineRead(LogRecordingContract):
    id: int
    recording_id: int
    pod_uid: str | None = None
    pod_name: str
    container_name: str
    log_time: datetime | None = None
    collected_at: datetime
    line_text: str
    normalized_fingerprint: str
    repeat_count: int = Field(ge=1)
    first_seen_at: datetime
    last_seen_at: datetime
    redacted: bool
    folded: bool
    byte_size: int = Field(ge=0)


class LogRecordingTemplateMatchRead(LogRecordingContract):
    id: int
    recording_id: int
    template_id: int | None = None
    template_name: str
    severity: str
    pod_name: str
    container_name: str
    keyword: str
    matched_context: str
    suggestion: str | None = None
    created_at: datetime


class LogRecordingLogPage(LogRecordingContract):
    items: list[LogRecordingLineRead]
    total: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    view: LogRecordingViewMode
    redacted: bool = True

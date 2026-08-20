from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Iterator
from typing import Protocol

from app.schemas.v1_1 import CollectionLimits, ProviderCollectionRequest, ProviderCollectionResult


@dataclass(frozen=True)
class TemporaryPodLogCollection:
    """Bounded in-memory log samples. Callers must not persist this object."""

    container_samples: dict[str, dict[str, str]] = field(default_factory=dict)
    previous_samples: dict[str, str] = field(default_factory=dict)
    log_pods_read: int = 0
    collected_log_bytes: int = 0
    truncated: bool = False
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None
    time_range_approximate: bool = False
    end_time_filter_precise: bool = True


class LogPodLimitExceededError(ValueError):
    def __init__(self, requested_pods: int, limit: int):
        self.requested_pods = requested_pods
        self.limit = limit
        super().__init__(
            f"日志巡检目标 {requested_pods} 个 Pod，超过上限 {limit}，请缩小范围"
        )


@dataclass(frozen=True)
class LogRecordingEntry:
    pod_uid: str | None
    pod_name: str
    container_name: str
    log_time: datetime | None
    text: str
    collected_at: datetime


@dataclass(frozen=True)
class LogRecordingPodSnapshot:
    namespace: str
    pod_uid: str
    pod_name: str
    node_name: str | None = None
    owner_kind: str | None = None
    owner_name: str | None = None
    container_names: list[str] = field(default_factory=list)
    entries: list[LogRecordingEntry] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass(frozen=True)
class LogRecordingSnapshot:
    namespace: str
    collected_at: datetime
    pods: list[LogRecordingPodSnapshot] = field(default_factory=list)
    total_bytes: int = 0
    truncated: bool = False


class InspectionProvider(Protocol):
    def list_namespaces(self) -> dict: ...

    def list_namespace_labels(self, namespace: str) -> dict: ...

    def list_namespace_pods(
        self,
        namespace: str,
        label_selector: str | None = None,
    ) -> dict: ...

    def list_namespace_pod_images(self, namespace: str) -> dict: ...

    def get_overview(self) -> dict: ...

    def run_cluster_inspection(
        self,
        *,
        include_logs: bool = False,
    ) -> dict: ...

    def run_namespace_inspection(
        self,
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = False,
        limits: CollectionLimits | None = None,
    ) -> dict: ...

    def run_pod_inspection(self, namespace: str, pod_name: str) -> dict: ...

    def collect_diagnosis_context(self, namespace: str, scope: str | None) -> dict: ...

    def collect_pod_log_samples(
        self,
        namespace: str,
        pod_names: list[str],
        limits: CollectionLimits,
        *,
        since_time: datetime | None = None,
        until_time: datetime | None = None,
    ) -> TemporaryPodLogCollection: ...

    def collect_log_recording_snapshot(
        self,
        namespace: str,
        *,
        since_time: datetime,
        max_pods: int,
        max_total_bytes: int,
        max_pod_bytes: int,
    ) -> LogRecordingSnapshot: ...

    def discover_log_recording_pods(
        self,
        namespace: str,
        *,
        max_pods: int,
    ) -> LogRecordingSnapshot: ...

    def stream_log_recording_entries(
        self,
        namespace: str,
        *,
        pod_uid: str,
        pod_name: str,
        container_name: str,
        since_time: datetime,
    ) -> Iterator[LogRecordingEntry]: ...

    def collect_resources(
        self,
        request: ProviderCollectionRequest,
    ) -> ProviderCollectionResult: ...

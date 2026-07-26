from dataclasses import dataclass, field
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


class LogPodLimitExceededError(ValueError):
    def __init__(self, requested_pods: int, limit: int):
        self.requested_pods = requested_pods
        self.limit = limit
        super().__init__(
            f"日志巡检目标 {requested_pods} 个 Pod，超过上限 {limit}，请缩小范围"
        )


class InspectionProvider(Protocol):
    def list_namespaces(self) -> dict: ...

    def list_namespace_labels(self, namespace: str) -> dict: ...

    def list_namespace_pods(
        self,
        namespace: str,
        label_selector: str | None = None,
    ) -> dict: ...

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
    ) -> TemporaryPodLogCollection: ...

    def collect_resources(
        self,
        request: ProviderCollectionRequest,
    ) -> ProviderCollectionResult: ...

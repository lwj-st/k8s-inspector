"""Frozen v1.1 API contracts.

This module deliberately contains DTOs only.  Persistence, scheduling, provider
collection and notification delivery belong to their respective implementation
modules.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from enum import Enum
from typing import Generic, Literal, TypeAlias, TypeVar
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @field_validator("*")
    @classmethod
    def require_timezone_aware_datetimes(cls, value: object) -> object:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must include a timezone")
        return value


class IssueSeverity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class IssueStatus(str, Enum):
    open = "open"
    recovered = "recovered"
    ignored = "ignored"


class IssueSortMode(str, Enum):
    priority = "priority"
    duration = "duration"
    last_changed = "last_changed"


class IssueScope(str, Enum):
    cluster = "cluster"
    namespace = "namespace"
    workload = "workload"
    pod = "pod"
    service = "service"
    ingress = "ingress"
    node = "node"
    storage = "storage"


class HealthStatus(str, Enum):
    healthy = "healthy"
    warning = "warning"
    critical = "critical"
    unknown = "unknown"


class CheckStatus(str, Enum):
    passed = "passed"
    abnormal = "abnormal"
    skipped = "skipped"
    failed = "failed"


class IssueCode(str, Enum):
    WORKLOAD_REPLICAS_UNAVAILABLE = "WORKLOAD_REPLICAS_UNAVAILABLE"
    WORKLOAD_ROLLOUT_STALLED = "WORKLOAD_ROLLOUT_STALLED"
    REQUIRED_COMPONENT_MISSING = "REQUIRED_COMPONENT_MISSING"
    JOB_FAILED = "JOB_FAILED"
    CRONJOB_NOT_SCHEDULED = "CRONJOB_NOT_SCHEDULED"
    SERVICE_NO_READY_ENDPOINT = "SERVICE_NO_READY_ENDPOINT"
    SERVICE_SELECTOR_MISMATCH = "SERVICE_SELECTOR_MISMATCH"
    INGRESS_BACKEND_NOT_FOUND = "INGRESS_BACKEND_NOT_FOUND"
    INGRESS_BACKEND_PORT_INVALID = "INGRESS_BACKEND_PORT_INVALID"
    INGRESS_CLASS_NOT_FOUND = "INGRESS_CLASS_NOT_FOUND"
    TLS_SECRET_NOT_FOUND = "TLS_SECRET_NOT_FOUND"
    TLS_CERT_EXPIRED = "TLS_CERT_EXPIRED"
    TLS_CERT_EXPIRING = "TLS_CERT_EXPIRING"
    TLS_HOST_MISMATCH = "TLS_HOST_MISMATCH"
    TLS_KEY_MISMATCH = "TLS_KEY_MISMATCH"
    PVC_NOT_BOUND = "PVC_NOT_BOUND"
    PV_FAILED = "PV_FAILED"
    PV_RELEASED_STALE = "PV_RELEASED_STALE"
    VOLUME_MOUNT_FAILED = "VOLUME_MOUNT_FAILED"
    NODE_NOT_READY = "NODE_NOT_READY"
    NODE_MEMORY_PRESSURE = "NODE_MEMORY_PRESSURE"
    NODE_DISK_PRESSURE = "NODE_DISK_PRESSURE"
    NODE_PID_PRESSURE = "NODE_PID_PRESSURE"
    NODE_NETWORK_UNAVAILABLE = "NODE_NETWORK_UNAVAILABLE"
    RESOURCE_USAGE_HIGH = "RESOURCE_USAGE_HIGH"
    INSPECTION_CHECK_FAILED = "INSPECTION_CHECK_FAILED"
    POD_NOT_READY = "POD_NOT_READY"
    POD_INIT_CONTAINER_FAILED = "POD_INIT_CONTAINER_FAILED"
    POD_IMAGE_PULL_FAILED = "POD_IMAGE_PULL_FAILED"
    POD_PROBE_FAILED = "POD_PROBE_FAILED"
    POD_CONFIG_REFERENCE_MISSING = "POD_CONFIG_REFERENCE_MISSING"
    POD_TERMINATING_STUCK = "POD_TERMINATING_STUCK"
    POD_RESTART_SPIKE = "POD_RESTART_SPIKE"
    POD_WARNING_EVENT = "POD_WARNING_EVENT"


class ResourceRef(ContractModel):
    api_version: str | None = Field(default=None, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    namespace: str | None = Field(default=None, max_length=253)
    name: str = Field(min_length=1, max_length=253)
    uid: str | None = Field(default=None, max_length=128)


class EvidenceSource(str, Enum):
    kubernetes_api = "kubernetes_api"
    metrics_api = "metrics_api"
    event = "event"
    log_match = "log_match"
    template = "template"
    derived = "derived"


JsonPrimitive: TypeAlias = str | int | float | bool | None
EvidenceFactValue: TypeAlias = JsonPrimitive | list[JsonPrimitive]

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "app_secret",
    "authorization",
    "cookie",
    "encryption_key",
    "password",
    "password_hash",
    "private_key",
    "raw_log",
    "raw_logs",
    "refresh_token",
    "secret_value",
    "session_token",
    "signing_secret",
    "tls_key",
    "token",
    "webhook_url",
}
_MAX_EVIDENCE_BYTES = 64 * 1024


def _reject_sensitive_keys(values: dict[str, object]) -> dict[str, object]:
    for key in values:
        normalized = key.casefold().replace("-", "_")
        if (
            normalized in _SENSITIVE_KEYS
            or normalized.endswith("_password")
            or normalized.endswith("_token")
            or normalized.endswith("_private_key")
            or normalized.endswith("_api_key")
            or normalized.endswith("_secret")
        ):
            raise ValueError(f"sensitive field is not allowed: {key}")
    return values


def _require_issue_evidence_size(evidence: list[Evidence]) -> None:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in evidence],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > _MAX_EVIDENCE_BYTES:
        raise ValueError("serialized evidence for one issue must not exceed 64 KiB")


class Evidence(ContractModel):
    code: str = Field(min_length=1, max_length=128)
    source: EvidenceSource
    summary: str = Field(min_length=1, max_length=2000)
    facts: dict[str, EvidenceFactValue] = Field(default_factory=dict)
    related_resources: list[ResourceRef] = Field(default_factory=list, max_length=50)
    observed_at: datetime
    truncated: bool = False

    @field_validator("facts")
    @classmethod
    def validate_facts(cls, value: dict[str, EvidenceFactValue]) -> dict[str, EvidenceFactValue]:
        _reject_sensitive_keys(value)
        for fact in value.values():
            if isinstance(fact, str) and len(fact) > 4096:
                raise ValueError("an evidence fact string must not exceed 4096 characters")
            if isinstance(fact, list):
                if len(fact) > 50:
                    raise ValueError("an evidence fact list must not contain more than 50 values")
                if any(isinstance(item, str) and len(item) > 4096 for item in fact):
                    raise ValueError("an evidence fact string must not exceed 4096 characters")
        return value

    @model_validator(mode="after")
    def enforce_serialized_size(self) -> Evidence:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > _MAX_EVIDENCE_BYTES:
            raise ValueError("serialized evidence must not exceed 64 KiB")
        return self


class Issue(ContractModel):
    id: int = Field(gt=0)
    cluster_id: str = Field(min_length=1, max_length=128)
    issue_code: IssueCode
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    severity: IssueSeverity
    status: IssueStatus
    scope: IssueScope
    resource: ResourceRef
    summary: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=4000)
    suggestion: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=32)
    first_seen_at: datetime
    last_seen_at: datetime
    recovered_at: datetime | None = None
    occurrence_count: int = Field(default=1, ge=1)
    source_check: str = Field(min_length=1, max_length=128)
    correlation_key: str | None = Field(default=None, max_length=256)
    acknowledged_at: datetime | None = None
    acknowledge_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Issue:
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at must not precede first_seen_at")
        if self.status == IssueStatus.recovered and self.recovered_at is None:
            raise ValueError("recovered_at is required for a recovered issue")
        if self.status in {IssueStatus.open, IssueStatus.ignored} and self.recovered_at is not None:
            raise ValueError("an open or ignored issue must not contain recovered_at")
        if self.recovered_at is not None and self.recovered_at < self.last_seen_at:
            raise ValueError("recovered_at must not precede last_seen_at")
        if self.acknowledge_note and self.acknowledged_at is None:
            raise ValueError("acknowledged_at is required when acknowledge_note is set")
        _require_issue_evidence_size(self.evidence)
        return self


class IssueFilterOption(ContractModel):
    value: str = Field(min_length=1, max_length=253)
    label: str = Field(min_length=1, max_length=253)


class IssueFilterOptions(ContractModel):
    namespaces: list[IssueFilterOption] = Field(default_factory=list)
    resource_kinds: list[IssueFilterOption] = Field(default_factory=list)
    source_checks: list[IssueFilterOption] = Field(default_factory=list)


class IssueCandidate(ContractModel):
    issue_code: IssueCode
    severity: IssueSeverity
    scope: IssueScope
    resource: ResourceRef
    summary: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=4000)
    suggestion: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=32)
    source_check: str = Field(min_length=1, max_length=128)
    correlation_key: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def enforce_evidence_size(self) -> IssueCandidate:
        _require_issue_evidence_size(self.evidence)
        return self


def build_issue_fingerprint(
    *,
    cluster_id: str,
    source_check: str,
    issue_code: IssueCode | str,
    resource: ResourceRef,
) -> str:
    """Build the only supported v1.1 fingerprint representation.

    Mutable text, severity, timestamps, Kubernetes UID and correlation_key are
    intentionally excluded.
    """

    normalized_cluster_id = cluster_id.strip()
    normalized_source_check = source_check.strip()
    if not normalized_cluster_id:
        raise ValueError("cluster_id must not be empty")
    if not normalized_source_check:
        raise ValueError("source_check must not be empty")

    code = issue_code.value if isinstance(issue_code, IssueCode) else IssueCode(issue_code).value
    canonical = {
        "cluster_id": normalized_cluster_id,
        "issue_code": code,
        "resource": {
            "kind": resource.kind.casefold(),
            "name": resource.name,
            "namespace": resource.namespace or "",
        },
        "source_check": normalized_source_check,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IssueEventType(str, Enum):
    opened = "opened"
    observed = "observed"
    severity_escalated = "severity_escalated"
    acknowledged = "acknowledged"
    ignored = "ignored"
    unignored = "unignored"
    recovered = "recovered"
    reopened = "reopened"


class InspectionTrigger(str, Enum):
    manual = "manual"
    scheduled = "scheduled"


class IssueEvent(ContractModel):
    id: int = Field(gt=0)
    issue_id: int = Field(gt=0)
    run_id: int | None = Field(default=None, gt=0)
    event_type: IssueEventType
    trigger: InspectionTrigger
    previous_status: IssueStatus | None = None
    new_status: IssueStatus | None = None
    previous_severity: IssueSeverity | None = None
    new_severity: IssueSeverity | None = None
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=1000)
    evidence_codes: list[str] = Field(default_factory=list, max_length=32)


class IssueAcknowledgeRequest(ContractModel):
    note: str = Field(min_length=1, max_length=1000)


class Coverage(ContractModel):
    check_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    status: CheckStatus
    reason: str | None = Field(default=None, max_length=2000)
    checked_objects: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    issue_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_non_pass_reason(self) -> Coverage:
        if self.status != CheckStatus.passed and not self.reason:
            raise ValueError("reason is required when a check did not pass")
        return self


class CollectionLayer(str, Enum):
    status = "status"
    evidence = "evidence"


class CollectionLimits(ContractModel):
    max_log_pods: int = Field(default=200, ge=1, le=1000)
    max_container_log_lines: int = Field(default=1000, ge=1, le=10000)
    max_log_bytes_per_pod: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    max_total_log_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    namespace_concurrency: int = Field(default=3, ge=1, le=10)


class RequiredComponentPolicy(ContractModel):
    name: str = Field(min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=253)
    kind: str = Field(min_length=1, max_length=128)
    label_selector: str = Field(min_length=1, max_length=1000)
    enabled: bool = True


def default_required_components() -> list[RequiredComponentPolicy]:
    return [
        RequiredComponentPolicy(
            name="Calico Node",
            namespace="kube-system",
            kind="DaemonSet",
            label_selector="k8s-app=calico-node",
        ),
        RequiredComponentPolicy(
            name="Calico Controllers",
            namespace="kube-system",
            kind="Deployment",
            label_selector="k8s-app=calico-kube-controllers",
        ),
        RequiredComponentPolicy(
            name="CoreDNS",
            namespace="kube-system",
            kind="Deployment",
            label_selector="k8s-app=kube-dns",
        ),
        RequiredComponentPolicy(
            name="etcd",
            namespace="kube-system",
            kind="Pod",
            label_selector="component=etcd",
        ),
        RequiredComponentPolicy(
            name="Kube APIServer",
            namespace="kube-system",
            kind="Pod",
            label_selector="component=kube-apiserver",
        ),
        RequiredComponentPolicy(
            name="Kube Controller Manager",
            namespace="kube-system",
            kind="Pod",
            label_selector="component=kube-controller-manager",
        ),
        RequiredComponentPolicy(
            name="Kube Scheduler",
            namespace="kube-system",
            kind="Pod",
            label_selector="component=kube-scheduler",
        ),
        RequiredComponentPolicy(
            name="Kube Proxy",
            namespace="kube-system",
            kind="DaemonSet",
            label_selector="k8s-app=kube-proxy",
        ),
        RequiredComponentPolicy(
            name="Metrics Server",
            namespace="kube-system",
            kind="Deployment",
            label_selector="k8s-app=metrics-server",
        ),
        RequiredComponentPolicy(
            name="Ingress NGINX Controller",
            namespace="ingress-nginx",
            kind="DaemonSet",
            label_selector="app.kubernetes.io/name=ingress-nginx,app.kubernetes.io/component=controller",
        ),
    ]


class InspectionThresholds(ContractModel):
    model_config = ConfigDict(frozen=True)

    tls_warning_days: int = Field(default=30, ge=1, le=3650)
    tls_critical_days: int = Field(default=7, ge=0, le=3650)
    pvc_pending_warning_minutes: int = Field(default=5, ge=1, le=10080)
    pvc_pending_critical_minutes: int = Field(default=30, ge=1, le=10080)
    pv_released_stale_hours: int = Field(default=24, ge=1, le=8760)
    job_incomplete_info_minutes: int = Field(default=60, ge=1, le=10080)
    resource_usage_warning_percent: int = Field(default=90, ge=1, le=100)
    resource_usage_consecutive_cycles: int = Field(default=3, ge=1, le=100)
    pod_terminating_warning_minutes: int = Field(default=10, ge=1, le=10080)
    pod_restart_window_minutes: int = Field(default=10, ge=1, le=1440)
    pod_restart_delta: int = Field(default=3, ge=1, le=10000)
    warning_event_window_minutes: int = Field(default=30, ge=1, le=10080)
    node_not_ready_grace_seconds: int = Field(default=0, ge=0, le=3600)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> InspectionThresholds:
        if self.tls_critical_days > self.tls_warning_days:
            raise ValueError("tls_critical_days must not exceed tls_warning_days")
        if self.pvc_pending_warning_minutes > self.pvc_pending_critical_minutes:
            raise ValueError("PVC warning threshold must not exceed critical threshold")
        return self


class DataRetentionSettings(ContractModel):
    inspection_run_days: int = Field(default=30, ge=7, le=180)
    recovered_issue_days: int = Field(default=90, ge=7, le=180)
    notification_delivery_days: int = Field(default=30, ge=7, le=180)
    security_audit_days: int = Field(default=90, ge=7, le=180)


class InspectionPolicySettings(ContractModel):
    required_components: list[RequiredComponentPolicy] = Field(default_factory=list, max_length=100)
    thresholds: InspectionThresholds = Field(default_factory=InspectionThresholds)
    retention: DataRetentionSettings = Field(default_factory=DataRetentionSettings)
    namespace_concurrency: int = Field(default=3, ge=1, le=10)
    max_log_pods: int = Field(default=200, ge=1, le=1000)

    @field_validator("required_components")
    @classmethod
    def reject_duplicate_component_locators(
        cls,
        value: list[RequiredComponentPolicy],
    ) -> list[RequiredComponentPolicy]:
        locators = [
            (
                item.namespace,
                item.kind.casefold(),
                item.label_selector,
            )
            for item in value
        ]
        if len(locators) != len(set(locators)):
            raise ValueError("required component locators must not contain duplicates")
        return value


class V11SettingsExtension(ContractModel):
    inspection_policy: InspectionPolicySettings = Field(default_factory=InspectionPolicySettings)


class V11SettingsUpdateExtension(ContractModel):
    inspection_policy: InspectionPolicySettings | None = None

    @model_validator(mode="after")
    def reject_explicit_null(self) -> V11SettingsUpdateExtension:
        if "inspection_policy" in self.model_fields_set and self.inspection_policy is None:
            raise ValueError("inspection_policy must be omitted or contain a complete policy")
        return self


class ProviderCollectionRequest(ContractModel):
    scope: InspectionScope
    layer: CollectionLayer
    thresholds: InspectionThresholds = Field(default_factory=InspectionThresholds)
    evidence_targets: list[ResourceRef] = Field(default_factory=list, max_length=1000)
    include_events: bool = False
    include_logs: bool = False
    trigger: InspectionTrigger
    limits: CollectionLimits = Field(default_factory=CollectionLimits)

    @model_validator(mode="after")
    def validate_layer(self) -> ProviderCollectionRequest:
        if self.layer == CollectionLayer.status:
            if self.evidence_targets or self.include_events or self.include_logs:
                raise ValueError("status collection cannot request evidence, events or logs")
        if self.layer == CollectionLayer.evidence and not self.evidence_targets:
            raise ValueError("evidence collection requires explicit evidence_targets")
        return self


class ProviderObservation(ContractModel):
    resource: ResourceRef
    observed_at: datetime
    observed_state: str | None = Field(default=None, max_length=256)
    facts: dict[str, EvidenceFactValue] = Field(default_factory=dict)
    related_resources: list[ResourceRef] = Field(default_factory=list, max_length=1000)

    @field_validator("facts")
    @classmethod
    def validate_facts(cls, value: dict[str, EvidenceFactValue]) -> dict[str, EvidenceFactValue]:
        _reject_sensitive_keys(value)
        return value


class ProviderCollectionFailure(ContractModel):
    check_code: str = Field(min_length=1, max_length=128)
    error_code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    resource: ResourceRef | None = None
    retryable: bool = False


class ProviderCollectionResult(ContractModel):
    layer: CollectionLayer
    observations: list[ProviderObservation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    failures: list[ProviderCollectionFailure] = Field(default_factory=list)
    kubernetes_api_calls: int = Field(default=0, ge=0)
    log_pods_read: int = Field(default=0, ge=0)
    collected_log_bytes: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class V11InspectionExtension(ContractModel):
    issues: list[Issue] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)


class InspectionScopeType(str, Enum):
    cluster = "cluster"
    namespace = "namespace"
    pod = "pod"


class InspectionScope(ContractModel):
    type: InspectionScopeType
    namespaces: list[str] = Field(default_factory=list, max_length=1000)
    namespace: str | None = Field(default=None, max_length=253)
    label_selector: str | None = Field(default=None, max_length=1000)
    pod_name: str | None = Field(default=None, max_length=253)

    @model_validator(mode="after")
    def validate_target(self) -> InspectionScope:
        if len(self.namespaces) != len(set(self.namespaces)):
            raise ValueError("namespaces must not contain duplicates")
        if self.type == InspectionScopeType.cluster:
            if self.namespaces or self.namespace or self.pod_name or self.label_selector:
                raise ValueError("cluster scope must not contain namespace, pod or selector fields")
        if self.type == InspectionScopeType.namespace:
            if bool(self.namespaces) == bool(self.namespace):
                raise ValueError("namespace scope requires exactly one of namespace or namespaces")
            if self.pod_name:
                raise ValueError("namespace scope must not contain pod_name")
        if self.type == InspectionScopeType.pod:
            if not self.namespace or not self.pod_name or self.namespaces or self.label_selector:
                raise ValueError("pod scope requires namespace and pod_name only")
        return self


def build_inspection_scope_key(scope: InspectionScope) -> str:
    """Build a stable identity for an already validated inspection scope."""

    canonical = {
        "label_selector": scope.label_selector or "",
        "namespace": scope.namespace or "",
        "namespaces": sorted(scope.namespaces),
        "pod_name": scope.pod_name or "",
        "type": scope.type.value,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CheckEvaluation(ContractModel):
    scope: InspectionScope
    scope_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage: Coverage
    issue_candidates: list[IssueCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> CheckEvaluation:
        if self.scope_key != build_inspection_scope_key(self.scope):
            raise ValueError("scope_key must match scope")
        if self.issue_candidates and self.coverage.status != CheckStatus.abnormal:
            raise ValueError("issue candidates require abnormal coverage")
        if self.coverage.issue_count != len(self.issue_candidates):
            raise ValueError("coverage.issue_count must match issue_candidates length")
        if any(candidate.source_check != self.coverage.check_code for candidate in self.issue_candidates):
            raise ValueError("issue candidate source_check must match coverage.check_code")
        return self


class InspectionCheckResult(Coverage):
    id: int = Field(gt=0)
    run_id: int = Field(gt=0)
    scope: InspectionScope
    scope_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: datetime

    @model_validator(mode="after")
    def validate_scope_key(self) -> InspectionCheckResult:
        if self.scope_key != build_inspection_scope_key(self.scope):
            raise ValueError("scope_key must match scope")
        return self


class InspectionRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial = "partial"
    failed = "failed"


class InspectionRun(ContractModel):
    id: int = Field(gt=0)
    plan_id: int | None = Field(default=None, gt=0)
    inspection_record_id: int | None = Field(default=None, gt=0)
    trigger: InspectionTrigger
    status: InspectionRunStatus
    scope: InspectionScope
    started_at: datetime | None = None
    finished_at: datetime | None = None
    coverage: list[Coverage] = Field(default_factory=list)
    issue_ids: list[int] = Field(default_factory=list)
    opened_issue_count: int = Field(default=0, ge=0)
    recovered_issue_count: int = Field(default=0, ge=0)
    kubernetes_api_calls: int = Field(default=0, ge=0)
    log_pods_read: int = Field(default=0, ge=0)
    collected_log_bytes: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_timing_and_failure(self) -> InspectionRun:
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.status == InspectionRunStatus.failed and not self.error_message:
            raise ValueError("error_message is required for a failed run")
        return self


class InspectionRunDetail(InspectionRun):
    check_results: list[InspectionCheckResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_check_results(self) -> InspectionRunDetail:
        if any(result.run_id != self.id for result in self.check_results):
            raise ValueError("check result run_id must match inspection run id")
        identities = [(result.check_code, result.scope_key) for result in self.check_results]
        if len(identities) != len(set(identities)):
            raise ValueError("check_results must not contain duplicate check_code and scope_key")
        return self


class PlanInterval(str, Enum):
    minutes_5 = "5m"
    minutes_10 = "10m"
    minutes_30 = "30m"
    minutes_60 = "60m"
    daily = "daily"


class PlanSchedule(ContractModel):
    interval: PlanInterval
    daily_at: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="UTC", min_length=1, max_length=128)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_daily_fields(self) -> PlanSchedule:
        if self.interval == PlanInterval.daily and self.daily_at is None:
            raise ValueError("daily_at is required for a daily schedule")
        if self.interval != PlanInterval.daily and self.daily_at is not None:
            raise ValueError("daily_at is only valid for a daily schedule")
        return self


class InspectionPlanScopeType(str, Enum):
    global_ = "global"
    namespaces = "namespaces"


class InspectionPlanScope(ContractModel):
    type: InspectionPlanScopeType
    namespaces: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_namespaces(self) -> InspectionPlanScope:
        if len(self.namespaces) != len(set(self.namespaces)):
            raise ValueError("namespaces must not contain duplicates")
        if self.type == InspectionPlanScopeType.namespaces and not self.namespaces:
            raise ValueError("namespace plan scope requires at least one namespace")
        if self.type == InspectionPlanScopeType.global_ and self.namespaces:
            raise ValueError("global plan scope must not contain namespaces")
        return self


class InspectionPlanCreate(ContractModel):
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    scope: InspectionPlanScope
    schedule: PlanSchedule
    include_template_matching: bool = True
    notification_channel_ids: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("notification_channel_ids")
    @classmethod
    def validate_channel_ids(cls, value: list[int]) -> list[int]:
        if any(channel_id <= 0 for channel_id in value):
            raise ValueError("notification channel ids must be positive")
        if len(value) != len(set(value)):
            raise ValueError("notification channel ids must not contain duplicates")
        return value


class InspectionPlanUpdate(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    scope: InspectionPlanScope | None = None
    schedule: PlanSchedule | None = None
    include_template_matching: bool | None = None
    notification_channel_ids: list[int] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_change(self) -> InspectionPlanUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.notification_channel_ids is not None:
            InspectionPlanCreate.validate_channel_ids(self.notification_channel_ids)
        return self


class InspectionPlan(InspectionPlanCreate):
    id: int = Field(gt=0)
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_run_status: InspectionRunStatus | None = None
    created_at: datetime
    updated_at: datetime


class NotificationChannelType(str, Enum):
    generic_webhook = "generic_webhook"
    feishu_custom_bot = "feishu_custom_bot"


_http_url_adapter = TypeAdapter(HttpUrl)


def _validated_secret_url(value: SecretStr | str) -> SecretStr:
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    validated = _http_url_adapter.validate_python(raw)
    return SecretStr(str(validated))


class NotificationChannelCreate(ContractModel):
    name: str = Field(min_length=1, max_length=128)
    type: NotificationChannelType
    enabled: bool = True
    webhook_url: SecretStr
    signing_secret: SecretStr | None = None
    mention_all_on_critical: bool = False
    timeout_seconds: int = Field(default=5, ge=1, le=30)

    @field_validator("webhook_url", mode="before")
    @classmethod
    def validate_webhook_url(cls, value: SecretStr | str) -> SecretStr:
        return _validated_secret_url(value)

    @model_validator(mode="after")
    def validate_provider_options(self) -> NotificationChannelCreate:
        if self.type == NotificationChannelType.generic_webhook and self.mention_all_on_critical:
            raise ValueError("mention_all_on_critical is only supported by feishu_custom_bot")
        if self.type == NotificationChannelType.feishu_custom_bot:
            parsed = urlsplit(self.webhook_url.get_secret_value())
            valid_path = re.fullmatch(r"/open-apis/bot/v2/hook/[^/]+/?", parsed.path)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "open.feishu.cn"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or valid_path is None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("feishu_custom_bot requires an official Feishu V2 webhook URL")
        return self


class NotificationChannelUpdate(ContractModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    webhook_url: SecretStr | None = None
    signing_secret: SecretStr | None = None
    clear_signing_secret: bool = False
    mention_all_on_critical: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)

    @field_validator("webhook_url", mode="before")
    @classmethod
    def validate_webhook_url(cls, value: SecretStr | str | None) -> SecretStr | None:
        return None if value is None else _validated_secret_url(value)

    @model_validator(mode="after")
    def require_change(self) -> NotificationChannelUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.signing_secret is not None and self.clear_signing_secret:
            raise ValueError("signing_secret and clear_signing_secret are mutually exclusive")
        return self


class NotificationChannel(ContractModel):
    id: int = Field(gt=0)
    name: str
    type: NotificationChannelType
    enabled: bool
    endpoint_masked: str = Field(min_length=1, max_length=512)
    signing_secret_configured: bool
    mention_all_on_critical: bool
    timeout_seconds: int = Field(ge=1, le=30)
    created_at: datetime
    updated_at: datetime


class WebhookTargetPolicy(ContractModel):
    allowed_hosts: list[str] = Field(default_factory=list, max_length=100)
    allowed_cidrs: list[str] = Field(default_factory=list, max_length=100)
    production_https_only: bool = True
    follow_redirects: Literal[False] = False
    block_private_networks: bool = True
    block_loopback: bool = True
    block_link_local: bool = True
    block_cloud_metadata: bool = True

    @field_validator("allowed_hosts")
    @classmethod
    def validate_hosts(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        hostname_pattern = re.compile(
            r"^(?:\*\.)?(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
        )
        for host in value:
            candidate = host.casefold().rstrip(".")
            if not hostname_pattern.fullmatch(candidate):
                raise ValueError(f"invalid allowed host: {host}")
            normalized.append(candidate)
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_hosts must not contain duplicates")
        return normalized

    @field_validator("allowed_cidrs")
    @classmethod
    def validate_cidrs(cls, value: list[str]) -> list[str]:
        normalized = [str(ipaddress.ip_network(cidr, strict=True)) for cidr in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_cidrs must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def require_allowlist(self) -> WebhookTargetPolicy:
        if not self.allowed_hosts and not self.allowed_cidrs:
            raise ValueError("at least one webhook target host or CIDR is required")
        return self


class NotificationEventType(str, Enum):
    issue_opened = "issue_opened"
    severity_escalated = "severity_escalated"
    issue_recovered = "issue_recovered"
    inspection_failed = "inspection_failed"
    flapping = "flapping"
    notification_test = "notification_test"


class NotificationMessage(ContractModel):
    event_type: NotificationEventType
    cluster_id: str = Field(min_length=1, max_length=128)
    issue_id: int | None = Field(default=None, gt=0)
    run_id: int | None = Field(default=None, gt=0)
    fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    issue_status: IssueStatus | None = None
    severity: IssueSeverity | None = None
    summary: str = Field(min_length=1, max_length=500)
    resource: ResourceRef | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime
    evidence_summaries: list[str] = Field(default_factory=list, max_length=20)
    suggestion: str | None = Field(default=None, max_length=2000)
    detail_url: HttpUrl
    mention_all: bool = False
    is_test: bool = False
    truncated: bool = False

    @model_validator(mode="after")
    def validate_event_content(self) -> NotificationMessage:
        issue_events = {
            NotificationEventType.issue_opened,
            NotificationEventType.severity_escalated,
            NotificationEventType.issue_recovered,
            NotificationEventType.flapping,
        }
        if self.event_type in issue_events:
            required = (
                self.issue_id,
                self.fingerprint,
                self.issue_status,
                self.severity,
                self.resource,
                self.first_seen_at,
            )
            if any(value is None for value in required):
                raise ValueError("issue notifications require issue identity, state, severity, resource and first_seen_at")
        if self.event_type == NotificationEventType.inspection_failed and self.run_id is None:
            raise ValueError("inspection_failed requires run_id")
        if self.event_type == NotificationEventType.notification_test and not self.is_test:
            raise ValueError("notification_test must set is_test=true")
        if self.mention_all and self.severity != IssueSeverity.critical:
            raise ValueError("mention_all is only allowed for critical notifications")
        return self


class NotificationDeliveryStatus(str, Enum):
    pending = "pending"
    delivering = "delivering"
    succeeded = "succeeded"
    failed = "failed"
    suppressed = "suppressed"


class NotificationDelivery(ContractModel):
    id: int = Field(gt=0)
    channel_id: int = Field(gt=0)
    deduplication_key: str = Field(min_length=1, max_length=256)
    issue_event_id: int | None = Field(default=None, gt=0)
    run_id: int | None = Field(default=None, gt=0)
    event_type: NotificationEventType
    status: NotificationDeliveryStatus
    attempt_count: int = Field(default=0, ge=0, le=3)
    http_status: int | None = Field(default=None, ge=100, le=599)
    provider_code: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=1000)
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_delivery_result(self) -> NotificationDelivery:
        if self.status == NotificationDeliveryStatus.succeeded and self.delivered_at is None:
            raise ValueError("delivered_at is required for successful delivery")
        if self.status == NotificationDeliveryStatus.failed and not self.error_code:
            raise ValueError("error_code is required for failed delivery")
        return self


class NotificationTestResponse(ContractModel):
    delivery: NotificationDelivery
    message: str = Field(min_length=1, max_length=500)


class ResourceMetricState(ContractModel):
    id: int = Field(gt=0)
    cluster_id: str = Field(min_length=1, max_length=128)
    resource: ResourceRef
    container_name: str | None = Field(default=None, max_length=253)
    sampled_at: datetime
    cpu_millicores: int | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)
    cpu_request_millicores: int | None = Field(default=None, ge=0)
    memory_request_bytes: int | None = Field(default=None, ge=0)
    cpu_limit_millicores: int | None = Field(default=None, ge=0)
    memory_limit_bytes: int | None = Field(default=None, ge=0)
    consecutive_cpu_over_threshold: int = Field(default=0, ge=0)
    consecutive_memory_over_threshold: int = Field(default=0, ge=0)
    stale: bool
    updated_at: datetime


class AuthLoginRequest(ContractModel):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr


class AuthPasswordChangeRequest(ContractModel):
    current_password: SecretStr
    new_password: SecretStr = Field(min_length=6, max_length=256)

    @model_validator(mode="after")
    def reject_same_password(self) -> "AuthPasswordChangeRequest":
        if self.current_password.get_secret_value() == self.new_password.get_secret_value():
            raise ValueError("new password must be different from current password")
        return self


class AdminSession(ContractModel):
    authenticated: bool
    username: str | None = Field(default=None, max_length=128)
    csrf_token: str | None = Field(default=None, min_length=16, max_length=512)
    idle_expires_at: datetime | None = None
    absolute_expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_authenticated_session(self) -> AdminSession:
        if self.authenticated:
            if not all((self.username, self.csrf_token, self.idle_expires_at, self.absolute_expires_at)):
                raise ValueError("authenticated session response is incomplete")
            if self.idle_expires_at and self.absolute_expires_at and self.idle_expires_at > self.absolute_expires_at:
                raise ValueError("idle expiry must not exceed absolute expiry")
        return self


class SecurityAuditAction(str, Enum):
    login_succeeded = "login_succeeded"
    login_failed = "login_failed"
    logout = "logout"
    session_revoked = "session_revoked"
    password_changed = "password_changed"
    configuration_changed = "configuration_changed"
    plan_changed = "plan_changed"
    notification_tested = "notification_tested"


class SecurityAuditOutcome(str, Enum):
    success = "success"
    denied = "denied"
    failed = "failed"


class SecurityAuditLog(ContractModel):
    id: int = Field(gt=0)
    action: SecurityAuditAction
    outcome: SecurityAuditOutcome
    actor: str | None = Field(default=None, max_length=128)
    source_ip: str | None = Field(default=None, max_length=64)
    occurred_at: datetime
    request_id: str | None = Field(default=None, max_length=128)
    details: dict[str, JsonPrimitive] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: dict[str, JsonPrimitive]) -> dict[str, JsonPrimitive]:
        _reject_sensitive_keys(value)
        return value


class ComponentState(str, Enum):
    ok = "ok"
    degraded = "degraded"
    failed = "failed"
    unavailable = "unavailable"


class SystemComponentStatus(ContractModel):
    state: ComponentState
    message: str = Field(min_length=1, max_length=1000)
    checked_at: datetime
    details: dict[str, JsonPrimitive] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: dict[str, JsonPrimitive]) -> dict[str, JsonPrimitive]:
        _reject_sensitive_keys(value)
        return value


class SystemStatus(ContractModel):
    status: Literal["healthy", "degraded", "not_ready"]
    version: str = Field(min_length=1, max_length=64)
    cluster_id: str = Field(min_length=1, max_length=128)
    database: SystemComponentStatus
    kubernetes_api: SystemComponentStatus
    provider: SystemComponentStatus
    scheduler: SystemComponentStatus
    metrics_api: SystemComponentStatus
    notifications: SystemComponentStatus
    last_inspection: SystemComponentStatus
    configuration: SystemComponentStatus
    kubernetes_server_version: str | None = Field(default=None, max_length=64)
    kubernetes_version_supported: bool | None = None


class LiveHealthResponse(ContractModel):
    status: Literal["live"] = "live"
    version: str = Field(min_length=1, max_length=64)


class ReadyHealthResponse(ContractModel):
    status: Literal["ready", "not_ready"]
    ready: bool
    reasons: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_ready_state(self) -> ReadyHealthResponse:
        if self.ready != (self.status == "ready"):
            raise ValueError("ready boolean must match status")
        if not self.ready and not self.reasons:
            raise ValueError("not_ready response requires at least one reason")
        return self


class ApiError(ContractModel):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)
    request_id: str | None = Field(default=None, max_length=128)
    details: dict[str, JsonPrimitive] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: dict[str, JsonPrimitive]) -> dict[str, JsonPrimitive]:
        _reject_sensitive_keys(value)
        return value


T = TypeVar("T")


class Page(ContractModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PageParams(ContractModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class IssueListFilter(PageParams):
    status: IssueStatus | None = None
    severity: IssueSeverity | None = None
    namespace: str | None = Field(default=None, max_length=253)
    resource_kind: str | None = Field(default=None, max_length=128)
    source_check: str | None = Field(default=None, max_length=128)
    sort: IssueSortMode = IssueSortMode.priority


class InspectionRunListFilter(PageParams):
    status: InspectionRunStatus | None = None
    trigger: InspectionTrigger | None = None
    plan_id: int | None = Field(default=None, gt=0)

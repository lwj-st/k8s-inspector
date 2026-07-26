"""Layered, read-only Kubernetes collection for the v1.1 contract."""

from __future__ import annotations

import copy
import re
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes.client.exceptions import ApiException

from app.providers.kubernetes_cron import (
    latest_cron_schedule as _latest_cron_schedule,
)
from app.providers.kubernetes_quantities import (
    quantity_bytes as _quantity_bytes,
    quantity_cpu_millicores as _quantity_cpu_millicores,
    sum_resources as _sum_resources,
)
from app.providers.kubernetes_restart_state import RestartSampleStore
from app.providers.kubernetes_tls import parse_tls_secret
from app.schemas.v1_1 import (
    CollectionLayer,
    Evidence,
    EvidenceSource,
    InspectionThresholds,
    ProviderCollectionFailure,
    ProviderCollectionRequest,
    ProviderCollectionResult,
    ProviderObservation,
    ResourceRef,
)


LogMatcher = Callable[[ResourceRef, str, str, bool, datetime], list[Evidence]]
_WARNING_EVENT_REASONS_WITH_CURRENT_FAULT = {
    "Failed",
    "FailedAttachVolume",
    "FailedMount",
    "FailedScheduling",
    "FailedCreatePodSandBox",
    "BackOff",
    "Unhealthy",
}
_PROBE_REASON_PATTERN = re.compile(r"(?:liveness|readiness|startup) probe failed", re.IGNORECASE)
_VOLUME_REASON_PATTERN = re.compile(r"(?:attach|mount|volume|binding)", re.IGNORECASE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _metadata_ref(obj: Any, kind: str, *, namespace: str | None = None) -> ResourceRef:
    metadata = getattr(obj, "metadata", None)
    return ResourceRef(
        api_version=getattr(obj, "api_version", None),
        kind=kind,
        namespace=namespace if namespace is not None else getattr(metadata, "namespace", None),
        name=getattr(metadata, "name", "unknown"),
        uid=str(getattr(metadata, "uid", "")) or None,
    )


def _condition_map(conditions: list[Any] | None) -> dict[str, Any]:
    return {str(getattr(item, "type", "")): item for item in conditions or []}


def _condition_true(conditions: dict[str, Any], name: str) -> bool:
    return str(getattr(conditions.get(name), "status", "")) == "True"


def _labels_as_list(labels: dict[str, str] | None) -> list[str]:
    return [f"{key}={value}" for key, value in sorted((labels or {}).items())]


def _age_minutes(timestamp: datetime | None, now: datetime) -> float:
    value = _aware(timestamp)
    return max(0.0, (now - value).total_seconds() / 60) if value else 0.0


def _matches_selector(labels: dict[str, str] | None, selector: dict[str, str] | None) -> bool:
    actual = labels or {}
    expected = selector or {}
    return bool(expected) and all(actual.get(key) == value for key, value in expected.items())


class KubernetesResourceCollector:
    """Collect sanitized observations with per-check failure isolation."""

    def __init__(
        self,
        *,
        settings: Any,
        core: Any,
        apps: Any,
        batch: Any,
        networking: Any,
        discovery: Any,
        storage: Any,
        custom: Any,
        version_api: Any,
        log_matcher: LogMatcher | None = None,
    ) -> None:
        self.settings = settings
        self.core = core
        self.apps = apps
        self.batch = batch
        self.networking = networking
        self.discovery = discovery
        self.storage = storage
        self.custom = custom
        self.version_api = version_api
        self.log_matcher = log_matcher
        self._api_calls = 0
        self._now = _utcnow()
        self._reference_cache: dict[
            tuple[str, str, str],
            bool,
        ] = {}
        self._restart_store = RestartSampleStore()
        self._thresholds = InspectionThresholds()

    @property
    def timeout(self) -> int:
        return int(getattr(self.settings, "k8s_request_timeout", 10) or 10)

    def _call(self, operation: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        self._api_calls += 1
        return operation(*args, **kwargs)

    def _failure(
        self,
        result: ProviderCollectionResult,
        *,
        check_code: str,
        exc: Exception,
        resource: ResourceRef | None = None,
    ) -> None:
        if isinstance(exc, ApiException):
            suffix = str(exc.status or "UNKNOWN")
            retryable = exc.status in {408, 429, 500, 502, 503, 504}
            reason = exc.reason or "Kubernetes API 请求失败"
        else:
            suffix = type(exc).__name__.upper()
            retryable = False
            reason = type(exc).__name__
        result.failures.append(
            ProviderCollectionFailure(
                check_code=check_code,
                error_code=f"KUBERNETES_API_{suffix}"[:128],
                message=f"{check_code} 采集失败：{reason}"[:2000],
                resource=resource,
                retryable=retryable,
            )
        )

    def collect(self, request: ProviderCollectionRequest) -> ProviderCollectionResult:
        # A shallow worker copy preserves immutable API clients and the locked
        # restart sample store, while all per-run counters/caches are isolated.
        worker = copy.copy(self)
        return worker._collect_once(request)

    def _collect_once(
        self,
        request: ProviderCollectionRequest,
    ) -> ProviderCollectionResult:
        started = time.monotonic()
        self._api_calls = 0
        self._now = _utcnow()
        self._reference_cache = {}
        self._thresholds = request.thresholds
        result = ProviderCollectionResult(layer=request.layer)
        if request.layer == CollectionLayer.evidence:
            self._collect_evidence(request, result)
        else:
            self._collect_status(request, result)
        result.kubernetes_api_calls = self._api_calls
        result.duration_ms = max(0, int((time.monotonic() - started) * 1000))
        return result

    def _collect_status(
        self,
        request: ProviderCollectionRequest,
        result: ProviderCollectionResult,
    ) -> None:
        try:
            result.observations.append(self.collect_server_version())
        except Exception as exc:  # failure is scoped and visible
            self._failure(result, check_code="kubernetes.version", exc=exc)

        scope = request.scope
        if scope.type.value == "pod":
            self._collect_single_pod_status(
                scope.namespace or "",
                scope.pod_name or "",
                result,
            )
            return

        if scope.type.value == "cluster":
            try:
                namespaces = self._call(
                    self.core.list_namespace,
                    _request_timeout=self.timeout,
                ).items
            except Exception as exc:
                self._failure(result, check_code="workload.status", exc=exc)
                self._failure(result, check_code="pod.runtime", exc=exc)
                return
            namespace_names = [item.metadata.name for item in namespaces]
            ingress_classes = self._list_ingress_classes(result)
            storage_class_modes = self._list_storage_class_modes(result)
        else:
            namespace_names = (
                list(scope.namespaces)
                if scope.namespaces
                else [scope.namespace or ""]
            )
            ingress_classes = None
            storage_class_modes = None

        for namespace in namespace_names:
            self._collect_namespace_status(
                namespace,
                scope.label_selector,
                result,
                ingress_classes=ingress_classes,
                storage_class_modes=storage_class_modes,
                include_metrics=scope.type.value != "cluster",
            )
        if scope.type.value == "cluster":
            self._collect_cluster_status(
                result,
                storage_class_modes=storage_class_modes or {},
            )

    def collect_server_version(self) -> ProviderObservation:
        version = self._call(
            self.version_api.get_code,
            _request_timeout=self.timeout,
        )
        git_version = str(getattr(version, "git_version", "") or "")
        major_text = str(getattr(version, "major", "") or "")
        minor_text = re.sub(r"\D.*$", "", str(getattr(version, "minor", "") or ""))
        try:
            major, minor = int(major_text), int(minor_text)
        except ValueError:
            match = re.search(r"v?(\d+)\.(\d+)", git_version)
            major, minor = (
                (int(match.group(1)), int(match.group(2)))
                if match
                else (0, 0)
            )
        return ProviderObservation(
            resource=ResourceRef(kind="KubernetesVersion", name="server"),
            observed_at=self._now,
            observed_state=git_version or f"{major}.{minor}",
            facts={
                "major": major,
                "minor": minor,
                "supported": major == 1 and 34 <= minor <= 36,
                "supported_range": "1.34-1.36",
            },
        )

    def _collect_namespace_status(
        self,
        namespace: str,
        selector: str | None,
        result: ProviderCollectionResult,
        *,
        ingress_classes: set[str] | None = None,
        storage_class_modes: dict[str, str | None] | None = None,
        include_metrics: bool = True,
    ) -> None:
        collections: dict[str, list[Any]] = {}
        calls = (
            ("pods", "pod.runtime", self.core.list_namespaced_pod, {"label_selector": selector}),
            ("services", "service.endpoints", self.core.list_namespaced_service, {}),
            ("deployments", "workload.status", self.apps.list_namespaced_deployment, {}),
            ("statefulsets", "workload.status", self.apps.list_namespaced_stateful_set, {}),
            ("daemonsets", "workload.status", self.apps.list_namespaced_daemon_set, {}),
            ("replicasets", "workload.status", self.apps.list_namespaced_replica_set, {}),
            ("jobs", "workload.status", self.batch.list_namespaced_job, {}),
            ("cronjobs", "workload.status", self.batch.list_namespaced_cron_job, {}),
            ("ingresses", "ingress.config_chain", self.networking.list_namespaced_ingress, {}),
            ("slices", "service.endpoints", self.discovery.list_namespaced_endpoint_slice, {}),
            (
                "pvcs",
                "storage.status",
                self.core.list_namespaced_persistent_volume_claim,
                {},
            ),
        )
        for key, check_code, operation, extra in calls:
            try:
                collections[key] = self._call(
                    operation,
                    namespace=namespace,
                    _request_timeout=self.timeout,
                    **extra,
                ).items
            except Exception as exc:
                collections[key] = []
                self._failure(
                    result,
                    check_code=check_code,
                    exc=exc,
                    resource=ResourceRef(
                        kind="Namespace",
                        name=namespace,
                    ),
                )
        if selector:
            collections = self._filter_collections_for_target_pods(
                collections
            )

        pods = collections["pods"]
        services = collections["services"]
        ingresses = collections["ingresses"]
        slices = collections["slices"]
        replicasets = collections["replicasets"]

        result.observations.extend(
            self._workload_observations(
                namespace,
                deployments=collections["deployments"],
                statefulsets=collections["statefulsets"],
                daemonsets=collections["daemonsets"],
                jobs=collections["jobs"],
                cronjobs=collections["cronjobs"],
                pods=pods,
                replicasets=replicasets,
                result=result,
            )
        )
        result.observations.extend(
            self._pod_observations(namespace, pods, replicasets, result)
        )
        ingress_services = self._ingress_service_names(ingresses)
        service_observations = self._service_observations(
            services,
            pods,
            slices,
            ingress_service_names=ingress_services,
        )
        result.observations.extend(service_observations)

        if ingress_classes is None:
            ingress_classes = self._list_ingress_classes(result)
        result.observations.extend(
            self._ingress_observations(
                ingresses,
                services,
                service_observations,
                ingress_classes,
            )
        )
        result.observations.extend(
            self._tls_observations(ingresses, result)
        )
        if storage_class_modes is None:
            storage_class_modes = self._list_storage_class_modes(result)
        result.observations.extend(
            self._pvc_observations(
                collections["pvcs"],
                pods,
                storage_class_modes,
            )
        )
        if include_metrics:
            self._collect_metrics(result, namespace=namespace, pods=pods)

    def _filter_collections_for_target_pods(
        self,
        collections: dict[str, list[Any]],
    ) -> dict[str, list[Any]]:
        pods = collections["pods"]
        pod_names = {pod.metadata.name for pod in pods}
        owner_map = self._pod_workload_owner_map(
            pods,
            collections["replicasets"],
        )
        related_workloads = set(owner_map.values())
        related_jobs = {
            name for kind_name, name in related_workloads if kind_name == "Job"
        }
        for job in collections["jobs"]:
            if job.metadata.name not in related_jobs:
                continue
            for owner in getattr(job.metadata, "owner_references", None) or []:
                if getattr(owner, "kind", None) == "CronJob":
                    related_workloads.add(("CronJob", owner.name))

        key_by_kind = {
            "deployments": "Deployment",
            "statefulsets": "StatefulSet",
            "daemonsets": "DaemonSet",
            "jobs": "Job",
            "cronjobs": "CronJob",
        }
        for key, kind_name in key_by_kind.items():
            collections[key] = [
                item
                for item in collections[key]
                if (kind_name, item.metadata.name) in related_workloads
            ]

        related_service_names: set[str] = set()
        for service in collections["services"]:
            selector = getattr(service.spec, "selector", None) or {}
            if any(
                selector
                and _matches_selector(
                    getattr(pod.metadata, "labels", None),
                    selector,
                )
                for pod in pods
            ):
                related_service_names.add(service.metadata.name)
        for endpoint_slice in collections["slices"]:
            if any(
                getattr(getattr(endpoint, "target_ref", None), "name", None)
                in pod_names
                for endpoint in getattr(endpoint_slice, "endpoints", None) or []
            ):
                labels = getattr(endpoint_slice.metadata, "labels", None) or {}
                service_name = labels.get("kubernetes.io/service-name")
                if service_name:
                    related_service_names.add(service_name)
        collections["services"] = [
            item
            for item in collections["services"]
            if item.metadata.name in related_service_names
        ]
        collections["slices"] = [
            item
            for item in collections["slices"]
            if (
                getattr(item.metadata, "labels", None) or {}
            ).get("kubernetes.io/service-name")
            in related_service_names
        ]
        collections["ingresses"] = [
            item
            for item in collections["ingresses"]
            if self._ingress_service_names([item]) & related_service_names
        ]

        related_claims = {
            getattr(
                getattr(volume, "persistent_volume_claim", None),
                "claim_name",
                None,
            )
            for pod in pods
            for volume in getattr(pod.spec, "volumes", None) or []
        }
        collections["pvcs"] = [
            item
            for item in collections["pvcs"]
            if item.metadata.name in related_claims
        ]
        return collections

    def _list_ingress_classes(
        self,
        result: ProviderCollectionResult,
    ) -> set[str]:
        try:
            return {
                item.metadata.name
                for item in self._call(
                    self.networking.list_ingress_class,
                    _request_timeout=self.timeout,
                ).items
            }
        except Exception as exc:
            self._failure(
                result,
                check_code="ingress.config_chain",
                exc=exc,
            )
            return set()

    def _list_storage_class_modes(
        self,
        result: ProviderCollectionResult,
    ) -> dict[str, str | None]:
        try:
            return {
                item.metadata.name: getattr(
                    item,
                    "volume_binding_mode",
                    None,
                )
                for item in self._call(
                    self.storage.list_storage_class,
                    _request_timeout=self.timeout,
                ).items
            }
        except Exception as exc:
            self._failure(result, check_code="storage.status", exc=exc)
            return {}

    def _collect_cluster_status(
        self,
        result: ProviderCollectionResult,
        *,
        storage_class_modes: dict[str, str | None],
    ) -> None:
        all_pods: list[Any] = []
        try:
            nodes = self._call(
                self.core.list_node,
                _request_timeout=self.timeout,
            ).items
            try:
                all_pods = self._call(
                    self.core.list_pod_for_all_namespaces,
                    _request_timeout=self.timeout,
                ).items
            except Exception as exc:
                all_pods = []
                self._failure(result, check_code="node.health", exc=exc)
            result.observations.extend(self._node_observations(nodes, all_pods))
        except Exception as exc:
            self._failure(result, check_code="node.health", exc=exc)

        try:
            pvs = self._call(
                self.core.list_persistent_volume,
                _request_timeout=self.timeout,
            ).items
            result.observations.extend(
                self._pv_observations(pvs, storage_class_modes)
            )
        except Exception as exc:
            self._failure(result, check_code="storage.status", exc=exc)

        self._collect_metrics(result, namespace=None, pods=all_pods)

    def _collect_single_pod_status(
        self,
        namespace: str,
        pod_name: str,
        result: ProviderCollectionResult,
    ) -> None:
        ref = ResourceRef(kind="Pod", namespace=namespace, name=pod_name)
        try:
            pod = self._call(
                self.core.read_namespaced_pod,
                name=pod_name,
                namespace=namespace,
                _request_timeout=self.timeout,
            )
        except Exception as exc:
            self._failure(result, check_code="pod.runtime", exc=exc, resource=ref)
            return
        result.observations.extend(
            self._pod_observations(namespace, [pod], [], result)
        )
        self._collect_metrics(
            result,
            namespace=namespace,
            pod_name=pod_name,
            pods=[pod],
        )

    def _workload_observations(
        self,
        namespace: str,
        *,
        deployments: list[Any],
        statefulsets: list[Any],
        daemonsets: list[Any],
        jobs: list[Any],
        cronjobs: list[Any],
        pods: list[Any],
        replicasets: list[Any],
        result: ProviderCollectionResult,
    ) -> list[ProviderObservation]:
        observations: list[ProviderObservation] = []
        pod_owners = self._pod_workload_owner_map(pods, replicasets)
        related_by_owner: dict[tuple[str, str], list[ResourceRef]] = defaultdict(list)
        for pod in pods:
            owner = pod_owners.get(pod.metadata.name)
            if owner:
                related_by_owner[owner].append(_metadata_ref(pod, "Pod"))

        for item in deployments:
            status = item.status
            conditions = _condition_map(getattr(status, "conditions", None))
            progress = conditions.get("Progressing")
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(item, "Deployment", namespace=namespace),
                    observed_at=self._now,
                    observed_state="paused" if bool(getattr(item.spec, "paused", False)) else "active",
                    facts={
                        "desired": int(getattr(item.spec, "replicas", 1) or 0),
                        "ready": int(getattr(status, "ready_replicas", 0) or 0),
                        "available": int(getattr(status, "available_replicas", 0) or 0),
                        "updated": int(getattr(status, "updated_replicas", 0) or 0),
                        "unavailable": int(getattr(status, "unavailable_replicas", 0) or 0),
                        "paused": bool(getattr(item.spec, "paused", False)),
                        "progress_deadline_exceeded": (
                            getattr(progress, "reason", None) == "ProgressDeadlineExceeded"
                        ),
                        "labels": _labels_as_list(getattr(item.metadata, "labels", None)),
                    },
                    related_resources=related_by_owner.get(("Deployment", item.metadata.name), []),
                )
            )
        for item in statefulsets:
            status = item.status
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(item, "StatefulSet", namespace=namespace),
                    observed_at=self._now,
                    observed_state="active",
                    facts={
                        "desired": int(getattr(item.spec, "replicas", 1) or 0),
                        "ready": int(getattr(status, "ready_replicas", 0) or 0),
                        "available": int(getattr(status, "available_replicas", 0) or 0),
                        "updated": int(getattr(status, "updated_replicas", 0) or 0),
                        "current_revision": str(getattr(status, "current_revision", "") or ""),
                        "update_revision": str(getattr(status, "update_revision", "") or ""),
                        "paused": False,
                        "labels": _labels_as_list(getattr(item.metadata, "labels", None)),
                    },
                    related_resources=related_by_owner.get(("StatefulSet", item.metadata.name), []),
                )
            )
        for item in daemonsets:
            status = item.status
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(item, "DaemonSet", namespace=namespace),
                    observed_at=self._now,
                    observed_state="active",
                    facts={
                        "desired": int(getattr(status, "desired_number_scheduled", 0) or 0),
                        "ready": int(getattr(status, "number_ready", 0) or 0),
                        "available": int(getattr(status, "number_available", 0) or 0),
                        "unavailable": int(getattr(status, "number_unavailable", 0) or 0),
                        "misscheduled": int(getattr(status, "number_misscheduled", 0) or 0),
                        "labels": _labels_as_list(getattr(item.metadata, "labels", None)),
                    },
                    related_resources=related_by_owner.get(("DaemonSet", item.metadata.name), []),
                )
            )
        for item in jobs:
            status = item.status
            conditions = _condition_map(getattr(status, "conditions", None))
            failure = conditions.get("Failed")
            complete = conditions.get("Complete")
            active_deadline = getattr(item.spec, "active_deadline_seconds", None)
            age = _age_minutes(getattr(item.metadata, "creation_timestamp", None), self._now)
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(item, "Job", namespace=namespace),
                    observed_at=self._now,
                    observed_state="complete" if _condition_true(conditions, "Complete") else "active",
                    facts={
                        "failed": int(getattr(status, "failed", 0) or 0),
                        "succeeded": int(getattr(status, "succeeded", 0) or 0),
                        "active": int(getattr(status, "active", 0) or 0),
                        "failure_condition": _condition_true(conditions, "Failed"),
                        "completion_condition": _condition_true(conditions, "Complete"),
                        "deadline_exceeded": getattr(failure, "reason", None) == "DeadlineExceeded",
                        "active_deadline_seconds": active_deadline,
                        "age_minutes": age,
                        "incomplete_info_minutes": 60,
                        "labels": _labels_as_list(getattr(item.metadata, "labels", None)),
                    },
                    related_resources=related_by_owner.get(("Job", item.metadata.name), []),
                )
            )
        job_owner_failures: dict[str, int] = defaultdict(int)
        for job in jobs:
            for owner in getattr(job.metadata, "owner_references", None) or []:
                if getattr(owner, "kind", None) == "CronJob" and int(getattr(job.status, "failed", 0) or 0) > 0:
                    job_owner_failures[getattr(owner, "name", "")] += 1
        for item in cronjobs:
            status = item.status
            schedule = str(getattr(item.spec, "schedule", "") or "")
            time_zone = str(getattr(item.spec, "time_zone", "") or "")
            last_schedule = _aware(
                getattr(status, "last_schedule_time", None)
            )
            try:
                latest_expected = _latest_cron_schedule(
                    schedule,
                    time_zone or "UTC",
                    self._now,
                )
                schedule_parse_error = False
            except ValueError:
                latest_expected = None
                schedule_parse_error = True
                result.failures.append(
                    ProviderCollectionFailure(
                        check_code="workload.status",
                        error_code="CRON_SCHEDULE_INVALID",
                        message=(
                            f"CronJob {namespace}/{item.metadata.name} "
                            "的 schedule 或 timeZone 无法解析"
                        ),
                        resource=_metadata_ref(
                            item,
                            "CronJob",
                            namespace=namespace,
                        ),
                    )
                )
            created_at = _aware(
                getattr(item.metadata, "creation_timestamp", None)
            )
            starting_deadline = getattr(
                item.spec,
                "starting_deadline_seconds",
                None,
            )
            missed_schedule = bool(
                latest_expected
                and latest_expected > (last_schedule or created_at or self._now)
                and (
                    starting_deadline is None
                    or (self._now - latest_expected).total_seconds()
                    > int(starting_deadline)
                )
            )
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(item, "CronJob", namespace=namespace),
                    observed_at=self._now,
                    observed_state="suspended" if bool(getattr(item.spec, "suspend", False)) else "active",
                    facts={
                        "suspended": bool(getattr(item.spec, "suspend", False)),
                        "schedule": schedule,
                        "time_zone": time_zone,
                        "starting_deadline_seconds": starting_deadline,
                        "last_schedule_age_minutes": _age_minutes(
                            getattr(status, "last_schedule_time", None),
                            self._now,
                        ),
                        "failed_jobs": job_owner_failures.get(item.metadata.name, 0),
                        "missed_schedule": missed_schedule,
                        "schedule_parse_error": schedule_parse_error,
                        "labels": _labels_as_list(getattr(item.metadata, "labels", None)),
                    },
                )
            )
        return observations

    def _pod_workload_owner_map(
        self,
        pods: list[Any],
        replicasets: list[Any],
    ) -> dict[str, tuple[str, str]]:
        rs_owners: dict[str, tuple[str, str]] = {}
        for rs in replicasets:
            owners = getattr(rs.metadata, "owner_references", None) or []
            deployment = next(
                (owner for owner in owners if getattr(owner, "kind", None) == "Deployment"),
                None,
            )
            rs_owners[rs.metadata.name] = (
                ("Deployment", deployment.name)
                if deployment
                else ("ReplicaSet", rs.metadata.name)
            )
        result: dict[str, tuple[str, str]] = {}
        for pod in pods:
            controller = next(
                (
                    owner
                    for owner in getattr(pod.metadata, "owner_references", None) or []
                    if bool(getattr(owner, "controller", False))
                ),
                None,
            )
            if not controller:
                continue
            if controller.kind == "ReplicaSet":
                result[pod.metadata.name] = rs_owners.get(
                    controller.name,
                    ("ReplicaSet", controller.name),
                )
            else:
                result[pod.metadata.name] = (controller.kind, controller.name)
        return result

    def _pod_observations(
        self,
        namespace: str,
        pods: list[Any],
        replicasets: list[Any],
        result: ProviderCollectionResult,
    ) -> list[ProviderObservation]:
        owner_map = self._pod_workload_owner_map(pods, replicasets)
        observations: list[ProviderObservation] = []
        for pod in pods:
            status = pod.status
            conditions = _condition_map(getattr(status, "conditions", None))
            phase = str(getattr(status, "phase", None) or "Unknown")
            completed = phase == "Succeeded"
            init_failure = ""
            image_pull_reason = ""
            last_terminated_reasons: list[str] = []
            terminated_reasons: list[str] = []
            restart_total = 0
            for container_status in (
                list(getattr(status, "init_container_statuses", None) or [])
                + list(getattr(status, "container_statuses", None) or [])
            ):
                state = getattr(container_status, "state", None)
                waiting = getattr(state, "waiting", None)
                terminated = getattr(state, "terminated", None)
                last_terminated = getattr(
                    getattr(container_status, "last_state", None),
                    "terminated",
                    None,
                )
                reason = str(getattr(waiting, "reason", "") or "")
                if container_status in (getattr(status, "init_container_statuses", None) or []):
                    if terminated and int(getattr(terminated, "exit_code", 0) or 0) != 0:
                        init_failure = str(getattr(terminated, "reason", "") or "Error")
                    elif reason and reason not in {"PodInitializing"}:
                        init_failure = reason
                if reason in {"ImagePullBackOff", "ErrImagePull"}:
                    image_pull_reason = reason
                if last_terminated:
                    last_terminated_reasons.append(
                        f"{getattr(container_status, 'name', '')}:"
                        f"{getattr(last_terminated, 'reason', '')}:"
                        f"{getattr(last_terminated, 'exit_code', '')}"
                    )
                if terminated:
                    terminated_reasons.append(
                        f"{getattr(container_status, 'name', '')}:"
                        f"{getattr(terminated, 'reason', '')}:"
                        f"{getattr(terminated, 'exit_code', '')}"
                    )
                restart_total += int(getattr(container_status, "restart_count", 0) or 0)

            missing_references = self._missing_pod_references(pod, result)
            related: list[ResourceRef] = []
            owner = owner_map.get(pod.metadata.name)
            if owner:
                related.append(
                    ResourceRef(
                        kind=owner[0],
                        namespace=namespace,
                        name=owner[1],
                    )
                )
            pvc_references = sorted(
                self._pod_references(pod)["PersistentVolumeClaim"]
            )
            related.extend(
                ResourceRef(
                    kind="PersistentVolumeClaim",
                    namespace=namespace,
                    name=name,
                )
                for name in pvc_references
            )
            deletion_timestamp = getattr(pod.metadata, "deletion_timestamp", None)
            restart_delta = self._restart_delta(pod, restart_total)
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(pod, "Pod", namespace=namespace),
                    observed_at=self._now,
                    observed_state=phase,
                    facts={
                        "phase": phase,
                        "status_reason": str(
                            getattr(status, "reason", "") or ""
                        ),
                        "ready": True if completed else _condition_true(conditions, "Ready"),
                        "scheduled": _condition_true(conditions, "PodScheduled"),
                        "unschedulable": getattr(conditions.get("PodScheduled"), "reason", None) == "Unschedulable",
                        "init_failure_reason": init_failure,
                        "image_pull_reason": image_pull_reason,
                        "last_terminated_reasons": last_terminated_reasons[:50],
                        "terminated_reasons": terminated_reasons[:50],
                        "restart_total": restart_total,
                        "restart_delta": restart_delta,
                        "restart_delta_threshold": (
                            self._thresholds.pod_restart_delta
                        ),
                        "deletion_age_minutes": _age_minutes(deletion_timestamp, self._now),
                        "terminating_warning_minutes": (
                            self._thresholds.pod_terminating_warning_minutes
                        ),
                        "missing_references": missing_references[:50],
                        "pvc_references": pvc_references[:50],
                        "node_name": str(getattr(pod.spec, "node_name", "") or ""),
                        "labels": _labels_as_list(getattr(pod.metadata, "labels", None)),
                        "warning_reasons": [],
                        "probe_failure": False,
                        "volume_mount_failure": False,
                    },
                    related_resources=related,
                )
            )
        return observations

    def _restart_delta(self, pod: Any, restart_total: int) -> int:
        key = str(getattr(pod.metadata, "uid", "") or "")
        if not key:
            key = (
                f"{getattr(pod.metadata, 'namespace', '')}/"
                f"{getattr(pod.metadata, 'name', '')}"
            )
        return self._restart_store.observe(
            key=key,
            restart_total=restart_total,
            observed_at=self._now,
            window_minutes=self._thresholds.pod_restart_window_minutes,
        )

    def _pod_references(self, pod: Any) -> dict[str, set[str]]:
        refs: dict[str, set[str]] = {
            "ConfigMap": set(),
            "Secret": set(),
            "ServiceAccount": set(),
            "PersistentVolumeClaim": set(),
        }
        spec = pod.spec
        service_account = getattr(spec, "service_account_name", None) or "default"
        refs["ServiceAccount"].add(service_account)
        for pull_secret in getattr(spec, "image_pull_secrets", None) or []:
            if getattr(pull_secret, "name", None):
                refs["Secret"].add(pull_secret.name)
        containers = (
            list(getattr(spec, "containers", None) or [])
            + list(getattr(spec, "init_containers", None) or [])
        )
        for container in containers:
            for source in getattr(container, "env_from", None) or []:
                cm = getattr(source, "config_map_ref", None)
                secret = getattr(source, "secret_ref", None)
                if cm and getattr(cm, "name", None) and not bool(getattr(cm, "optional", False)):
                    refs["ConfigMap"].add(cm.name)
                if secret and getattr(secret, "name", None) and not bool(getattr(secret, "optional", False)):
                    refs["Secret"].add(secret.name)
            for env in getattr(container, "env", None) or []:
                value_from = getattr(env, "value_from", None)
                cm = getattr(value_from, "config_map_key_ref", None)
                secret = getattr(value_from, "secret_key_ref", None)
                if cm and getattr(cm, "name", None) and not bool(getattr(cm, "optional", False)):
                    refs["ConfigMap"].add(cm.name)
                if secret and getattr(secret, "name", None) and not bool(getattr(secret, "optional", False)):
                    refs["Secret"].add(secret.name)
        for volume in getattr(spec, "volumes", None) or []:
            cm = getattr(volume, "config_map", None)
            secret = getattr(volume, "secret", None)
            pvc = getattr(volume, "persistent_volume_claim", None)
            if cm and getattr(cm, "name", None) and not bool(getattr(cm, "optional", False)):
                refs["ConfigMap"].add(cm.name)
            if secret and getattr(secret, "secret_name", None) and not bool(getattr(secret, "optional", False)):
                refs["Secret"].add(secret.secret_name)
            if pvc and getattr(pvc, "claim_name", None):
                refs["PersistentVolumeClaim"].add(pvc.claim_name)
            projected = getattr(volume, "projected", None)
            for source in getattr(projected, "sources", None) or []:
                cm_source = getattr(source, "config_map", None)
                secret_source = getattr(source, "secret", None)
                if cm_source and getattr(cm_source, "name", None) and not bool(getattr(cm_source, "optional", False)):
                    refs["ConfigMap"].add(cm_source.name)
                if secret_source and getattr(secret_source, "name", None) and not bool(getattr(secret_source, "optional", False)):
                    refs["Secret"].add(secret_source.name)
        return refs

    def _missing_pod_references(
        self,
        pod: Any,
        result: ProviderCollectionResult,
    ) -> list[str]:
        namespace = pod.metadata.namespace
        pod_ref = _metadata_ref(pod, "Pod")
        missing: list[str] = []
        operations = {
            "ConfigMap": self.core.read_namespaced_config_map,
            "Secret": self.core.read_namespaced_secret,
            "ServiceAccount": self.core.read_namespaced_service_account,
            "PersistentVolumeClaim": self.core.read_namespaced_persistent_volume_claim,
        }
        for kind, names in self._pod_references(pod).items():
            for name in sorted(names):
                cache_key = (namespace, kind, name)
                cached = self._reference_cache.get(cache_key)
                if cached is not None:
                    if not cached:
                        missing.append(f"{kind}/{name}")
                    continue
                try:
                    obj = self._call(
                        operations[kind],
                        name=name,
                        namespace=namespace,
                        _request_timeout=self.timeout,
                    )
                    if kind in {"Secret", "ConfigMap"}:
                        # The object is used only for existence. Drop payload
                        # immediately and never sanitize it into a DTO.
                        if hasattr(obj, "data"):
                            obj.data = None
                        if hasattr(obj, "binary_data"):
                            obj.binary_data = None
                        del obj
                    self._reference_cache[cache_key] = True
                except ApiException as exc:
                    if exc.status == 404:
                        self._reference_cache[cache_key] = False
                        missing.append(f"{kind}/{name}")
                    else:
                        self._failure(
                            result,
                            check_code="pod.runtime",
                            exc=exc,
                            resource=pod_ref,
                        )
                except Exception as exc:
                    self._failure(
                        result,
                        check_code="pod.runtime",
                        exc=exc,
                        resource=pod_ref,
                    )
        return missing

    def _ingress_service_names(self, ingresses: list[Any]) -> set[str]:
        names: set[str] = set()
        for ingress in ingresses:
            for backend in self._ingress_backends(ingress):
                service = getattr(backend, "service", None)
                if service and getattr(service, "name", None):
                    names.add(service.name)
        return names

    def _service_observations(
        self,
        services: list[Any],
        pods: list[Any],
        slices: list[Any],
        *,
        ingress_service_names: set[str],
    ) -> list[ProviderObservation]:
        slices_by_service: dict[str, list[Any]] = defaultdict(list)
        for endpoint_slice in slices:
            labels = getattr(endpoint_slice.metadata, "labels", None) or {}
            service_name = labels.get("kubernetes.io/service-name")
            if service_name:
                slices_by_service[service_name].append(endpoint_slice)
        observations: list[ProviderObservation] = []
        for service in services:
            selector = getattr(service.spec, "selector", None) or {}
            selected_pods = [
                pod
                for pod in pods
                if selector and _matches_selector(getattr(pod.metadata, "labels", None), selector)
            ]
            related: list[ResourceRef] = [
                _metadata_ref(pod, "Pod") for pod in selected_pods
            ]
            service_slices = slices_by_service.get(service.metadata.name, [])
            ready = 0
            for endpoint_slice in service_slices:
                for endpoint in getattr(endpoint_slice, "endpoints", None) or []:
                    condition = getattr(
                        getattr(endpoint, "conditions", None),
                        "ready",
                        None,
                    )
                    # Kubernetes semantics: omitted ready means ready.
                    if condition is not False:
                        ready += 1
                    target = getattr(endpoint, "target_ref", None)
                    if target and getattr(target, "name", None):
                        ref = ResourceRef(
                            kind=getattr(target, "kind", "Pod"),
                            namespace=getattr(target, "namespace", None),
                            name=target.name,
                            uid=str(getattr(target, "uid", "")) or None,
                        )
                        if ref not in related:
                            related.append(ref)
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(service, "Service"),
                    observed_at=self._now,
                    observed_state=str(getattr(service.spec, "type", None) or "ClusterIP"),
                    facts={
                        "service_type": str(getattr(service.spec, "type", None) or "ClusterIP"),
                        "selector_present": bool(selector),
                        "selector": _labels_as_list(selector),
                        "selected_pods": len(selected_pods),
                        "endpoint_slices": len(service_slices),
                        "ready_endpoints": ready,
                        "ingress_referenced": service.metadata.name in ingress_service_names,
                        "headless": getattr(service.spec, "cluster_ip", None) == "None",
                        "ports": [
                            str(getattr(port, "name", "") or getattr(port, "port", ""))
                            for port in getattr(service.spec, "ports", None) or []
                        ][:50],
                    },
                    related_resources=related[:1000],
                )
            )
        return observations

    def _ingress_backends(self, ingress: Any) -> list[Any]:
        spec = ingress.spec
        backends: list[Any] = []
        default_backend = getattr(spec, "default_backend", None)
        if default_backend:
            backends.append(default_backend)
        for rule in getattr(spec, "rules", None) or []:
            http = getattr(rule, "http", None)
            for path in getattr(http, "paths", None) or []:
                if getattr(path, "backend", None):
                    backends.append(path.backend)
        return backends

    def _service_port_exists(self, service: Any, backend_port: Any) -> bool:
        name = getattr(backend_port, "name", None)
        number = getattr(backend_port, "number", None)
        return any(
            (name and getattr(port, "name", None) == name)
            or (number is not None and getattr(port, "port", None) == number)
            for port in getattr(service.spec, "ports", None) or []
        )

    def _ingress_observations(
        self,
        ingresses: list[Any],
        services: list[Any],
        service_observations: list[ProviderObservation],
        ingress_classes: set[str],
    ) -> list[ProviderObservation]:
        service_by_name = {item.metadata.name: item for item in services}
        ready_by_service = {
            item.resource.name: int(item.facts.get("ready_endpoints") or 0)
            for item in service_observations
        }
        observations: list[ProviderObservation] = []
        for ingress in ingresses:
            missing: list[str] = []
            invalid_ports: list[str] = []
            no_ready: list[str] = []
            resource_backends = 0
            service_backends = 0
            related: list[ResourceRef] = []
            for backend in self._ingress_backends(ingress):
                service_backend = getattr(backend, "service", None)
                if service_backend is None:
                    resource_backends += 1
                    continue
                service_backends += 1
                service_name = service_backend.name
                service = service_by_name.get(service_name)
                related.append(
                    ResourceRef(
                        kind="Service",
                        namespace=ingress.metadata.namespace,
                        name=service_name,
                    )
                )
                if service is None:
                    missing.append(service_name)
                    continue
                port = getattr(service_backend, "port", None)
                if not self._service_port_exists(service, port):
                    display = getattr(port, "name", None) or getattr(port, "number", None)
                    invalid_ports.append(f"{service_name}:{display}")
                if ready_by_service.get(service_name, 0) == 0:
                    no_ready.append(service_name)
            ingress_class = getattr(ingress.spec, "ingress_class_name", None)
            hosts = [
                str(getattr(rule, "host", "") or "")
                for rule in getattr(ingress.spec, "rules", None) or []
                if getattr(rule, "host", None)
            ]
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(ingress, "Ingress"),
                    observed_at=self._now,
                    observed_state="configured",
                    facts={
                        "service_backends": service_backends,
                        "resource_backends": resource_backends,
                        "missing_backend_services": missing[:50],
                        "invalid_backend_ports": invalid_ports[:50],
                        "services_without_ready_endpoints": no_ready[:50],
                        "ingress_class": str(ingress_class or ""),
                        "missing_ingress_class": (
                            str(ingress_class)
                            if ingress_class and ingress_class not in ingress_classes
                            else ""
                        ),
                        "hosts": hosts[:50],
                        "config_chain_only": True,
                    },
                    related_resources=related[:1000],
                )
            )
        return observations

    def _tls_observations(
        self,
        ingresses: list[Any],
        result: ProviderCollectionResult,
    ) -> list[ProviderObservation]:
        refs: dict[tuple[str, str], set[str]] = defaultdict(set)
        related_ingresses: dict[
            tuple[str, str],
            list[ResourceRef],
        ] = defaultdict(list)
        for ingress in ingresses:
            namespace = ingress.metadata.namespace
            for tls in getattr(ingress.spec, "tls", None) or []:
                name = getattr(tls, "secret_name", None)
                if name:
                    refs[(namespace, name)].update(
                        str(host) for host in getattr(tls, "hosts", None) or []
                    )
                    related_ingresses[(namespace, name)].append(
                        _metadata_ref(ingress, "Ingress")
                    )
        observations: list[ProviderObservation] = []
        for (namespace, name), hosts in refs.items():
            ref = ResourceRef(kind="TLSSecret", namespace=namespace, name=name)
            try:
                secret = self._call(
                    self.core.read_namespaced_secret,
                    name=name,
                    namespace=namespace,
                    _request_timeout=self.timeout,
                )
            except ApiException as exc:
                if exc.status == 404:
                    observations.append(
                        ProviderObservation(
                            resource=ref,
                            observed_at=self._now,
                            observed_state="missing",
                            facts={"exists": False, "hosts": sorted(hosts)[:50]},
                            related_resources=related_ingresses[
                                (namespace, name)
                            ][:1000],
                        )
                    )
                else:
                    self._failure(
                        result,
                        check_code="tls.certificate",
                        exc=exc,
                        resource=ref,
                    )
                continue
            except Exception as exc:
                self._failure(
                    result,
                    check_code="tls.certificate",
                    exc=exc,
                    resource=ref,
                )
                continue
            facts = self._parse_tls_secret(secret, hosts)
            if hasattr(secret, "data"):
                secret.data = None
            del secret
            observations.append(
                ProviderObservation(
                    resource=ref,
                    observed_at=self._now,
                    observed_state="parsed" if facts["parse_ok"] else "invalid",
                    facts=facts,
                    related_resources=related_ingresses[
                        (namespace, name)
                    ][:1000],
                )
            )
        return observations

    def _parse_tls_secret(self, secret: Any, hosts: set[str]) -> dict[str, Any]:
        """Compatibility wrapper; parsing is isolated in ``kubernetes_tls``."""

        return parse_tls_secret(secret, hosts, now=self._now)

    def _pvc_observations(
        self,
        pvcs: list[Any],
        pods: list[Any],
        storage_class_modes: dict[str, str | None],
    ) -> list[ProviderObservation]:
        consumers: dict[str, list[ResourceRef]] = defaultdict(list)
        for pod in pods:
            for volume in getattr(pod.spec, "volumes", None) or []:
                pvc = getattr(volume, "persistent_volume_claim", None)
                if pvc and getattr(pvc, "claim_name", None):
                    consumers[pvc.claim_name].append(_metadata_ref(pod, "Pod"))
        observations: list[ProviderObservation] = []
        for pvc in pvcs:
            phase = str(getattr(pvc.status, "phase", None) or "Unknown")
            annotations = getattr(pvc.metadata, "annotations", None) or {}
            binding_mode = annotations.get("volume.kubernetes.io/selected-node")
            storage_class = str(
                getattr(pvc.spec, "storage_class_name", "") or ""
            )
            volume_name = str(getattr(pvc.spec, "volume_name", "") or "")
            related = list(consumers.get(pvc.metadata.name, []))
            if volume_name:
                related.append(
                    ResourceRef(kind="PersistentVolume", name=volume_name)
                )
            if storage_class:
                related.append(
                    ResourceRef(kind="StorageClass", name=storage_class)
                )
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(pvc, "PersistentVolumeClaim"),
                    observed_at=self._now,
                    observed_state=phase,
                    facts={
                        "phase": phase,
                        "pending_minutes": _age_minutes(
                            getattr(pvc.metadata, "creation_timestamp", None),
                            self._now,
                        )
                        if phase == "Pending"
                        else 0.0,
                        "storage_class": storage_class,
                        "volume_binding_mode": str(
                            storage_class_modes.get(storage_class) or ""
                        ),
                        "consumer_pods": len(consumers.get(pvc.metadata.name, [])),
                        "selected_node": str(binding_mode or ""),
                        "volume_name": volume_name,
                    },
                    related_resources=related[:1000],
                )
            )
        return observations

    def _pv_observations(
        self,
        pvs: list[Any],
        storage_class_modes: dict[str, str | None],
    ) -> list[ProviderObservation]:
        observations: list[ProviderObservation] = []
        for pv in pvs:
            phase = str(getattr(pv.status, "phase", None) or "Unknown")
            transition = getattr(pv.status, "last_phase_transition_time", None)
            storage_class = str(getattr(pv.spec, "storage_class_name", "") or "")
            claim_ref = getattr(pv.spec, "claim_ref", None)
            claim_name = str(getattr(claim_ref, "name", "") or "")
            claim_namespace = str(getattr(claim_ref, "namespace", "") or "")
            related: list[ResourceRef] = []
            if claim_name:
                related.append(
                    ResourceRef(
                        kind="PersistentVolumeClaim",
                        namespace=claim_namespace or None,
                        name=claim_name,
                        uid=str(getattr(claim_ref, "uid", "") or "") or None,
                    )
                )
            if storage_class:
                related.append(
                    ResourceRef(kind="StorageClass", name=storage_class)
                )
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(pv, "PersistentVolume", namespace=None),
                    observed_at=self._now,
                    observed_state=phase,
                    facts={
                        "phase": phase,
                        "reclaim_policy": str(getattr(pv.spec, "persistent_volume_reclaim_policy", "") or ""),
                        "released_hours": (
                            _age_minutes(transition, self._now) / 60
                            if phase == "Released"
                            else 0.0
                        ),
                        "storage_class": storage_class,
                        "volume_binding_mode": str(storage_class_modes.get(storage_class) or ""),
                        "claim_name": claim_name,
                        "claim_namespace": claim_namespace,
                    },
                    related_resources=related,
                )
            )
        return observations

    def _node_observations(
        self,
        nodes: list[Any],
        pods: list[Any],
    ) -> list[ProviderObservation]:
        requests_by_node: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        abnormal_by_node: dict[str, int] = defaultdict(int)
        for pod in pods:
            node_name = getattr(pod.spec, "node_name", None)
            if not node_name or getattr(pod.status, "phase", None) in {"Succeeded", "Failed"}:
                continue
            cpu, memory = _sum_resources(pod, "requests")
            old_cpu, old_memory = requests_by_node[node_name]
            requests_by_node[node_name] = (old_cpu + cpu, old_memory + memory)
            conditions = _condition_map(getattr(pod.status, "conditions", None))
            if not _condition_true(conditions, "Ready"):
                abnormal_by_node[node_name] += 1
        observations: list[ProviderObservation] = []
        for node in nodes:
            conditions = _condition_map(getattr(node.status, "conditions", None))
            ready = str(getattr(conditions.get("Ready"), "status", "") or "Unknown")
            allocatable = getattr(node.status, "allocatable", None) or {}
            requests_cpu, requests_memory = requests_by_node[node.metadata.name]
            observations.append(
                ProviderObservation(
                    resource=_metadata_ref(node, "Node", namespace=None),
                    observed_at=self._now,
                    observed_state=f"Ready={ready}",
                    facts={
                        "ready_status": ready,
                        "ready_age_seconds": (
                            _age_minutes(
                                getattr(
                                    conditions.get("Ready"),
                                    "last_transition_time",
                                    None,
                                ),
                                self._now,
                            )
                            * 60
                        ),
                        "memory_pressure": _condition_true(conditions, "MemoryPressure"),
                        "disk_pressure": _condition_true(conditions, "DiskPressure"),
                        "pid_pressure": _condition_true(conditions, "PIDPressure"),
                        "network_unavailable": _condition_true(conditions, "NetworkUnavailable"),
                        "unschedulable": bool(getattr(node.spec, "unschedulable", False)),
                        "taints": [
                            f"{getattr(item, 'key', '')}={getattr(item, 'value', '')}:{getattr(item, 'effect', '')}"
                            for item in getattr(node.spec, "taints", None) or []
                        ][:50],
                        "allocatable_cpu_millicores": _quantity_cpu_millicores(allocatable.get("cpu")) or 0,
                        "allocatable_memory_bytes": _quantity_bytes(allocatable.get("memory")) or 0,
                        "requested_cpu_millicores": requests_cpu,
                        "requested_memory_bytes": requests_memory,
                        "abnormal_pods": abnormal_by_node[node.metadata.name],
                        "business_impact": abnormal_by_node[node.metadata.name] > 0,
                    },
                )
            )
        return observations

    def _collect_metrics(
        self,
        result: ProviderCollectionResult,
        *,
        namespace: str | None,
        pod_name: str | None = None,
        pods: list[Any] | None = None,
    ) -> None:
        try:
            if namespace:
                payload = self._call(
                    self.custom.list_namespaced_custom_object,
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                    _request_timeout=self.timeout,
                )
            else:
                payload = self._call(
                    self.custom.list_cluster_custom_object,
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="pods",
                    _request_timeout=self.timeout,
                )
        except ApiException as exc:
            if exc.status not in {404, 503}:
                self._failure(result, check_code="metrics.resource", exc=exc)
            return
        except Exception as exc:
            self._failure(result, check_code="metrics.resource", exc=exc)
            return
        pod_specs = {
            (pod.metadata.namespace, pod.metadata.name): pod
            for pod in pods or []
        }
        for item in payload.get("items", []):
            metadata = item.get("metadata") or {}
            name = str(metadata.get("name") or "")
            item_namespace = str(metadata.get("namespace") or namespace or "")
            if pod_name and name != pod_name:
                continue
            timestamp = self._parse_timestamp(item.get("timestamp"))
            stale = (self._now - timestamp).total_seconds() > 300
            cpu = memory = 0
            for container in item.get("containers") or []:
                usage = container.get("usage") or {}
                cpu += _quantity_cpu_millicores(usage.get("cpu")) or 0
                memory += _quantity_bytes(usage.get("memory")) or 0
            pod = pod_specs.get((item_namespace, name))
            request_cpu = request_memory = limit_cpu = limit_memory = 0
            if pod is not None:
                request_cpu, request_memory = _sum_resources(pod, "requests")
                limit_cpu, limit_memory = _sum_resources(pod, "limits")
            result.observations.append(
                ProviderObservation(
                    resource=ResourceRef(
                        kind="PodMetric",
                        namespace=item_namespace,
                        name=name,
                    ),
                    observed_at=timestamp,
                    observed_state="stale" if stale else "current",
                    facts={
                        "metrics_available": True,
                        "stale": stale,
                        "cpu_usage_millicores": cpu,
                        "memory_usage_bytes": memory,
                        "cpu_request_millicores": request_cpu,
                        "memory_request_bytes": request_memory,
                        "cpu_limit_millicores": limit_cpu or None,
                        "memory_limit_bytes": limit_memory or None,
                        "cpu_request_percent": (
                            cpu * 100 / request_cpu if request_cpu else None
                        ),
                        "memory_request_percent": (
                            memory * 100 / request_memory
                            if request_memory
                            else None
                        ),
                        "cpu_limit_percent": (
                            cpu * 100 / limit_cpu if limit_cpu else None
                        ),
                        "memory_limit_percent": (
                            memory * 100 / limit_memory
                            if limit_memory
                            else None
                        ),
                        # Consecutive count is enriched by orchestration from
                        # ResourceMetricState; the collector never invents it.
                        "consecutive_cpu_over_threshold": 0,
                        "consecutive_memory_over_threshold": 0,
                    },
                )
            )
        if namespace is None:
            self._collect_node_metrics(result)

    def _collect_node_metrics(
        self,
        result: ProviderCollectionResult,
    ) -> None:
        try:
            payload = self._call(
                self.custom.list_cluster_custom_object,
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
                _request_timeout=self.timeout,
            )
        except ApiException as exc:
            if exc.status not in {404, 503}:
                self._failure(result, check_code="metrics.resource", exc=exc)
            return
        except Exception as exc:
            self._failure(result, check_code="metrics.resource", exc=exc)
            return
        for item in payload.get("items", []):
            metadata = item.get("metadata") or {}
            usage = item.get("usage") or {}
            timestamp = self._parse_timestamp(item.get("timestamp"))
            result.observations.append(
                ProviderObservation(
                    resource=ResourceRef(
                        kind="NodeMetric",
                        name=str(metadata.get("name") or ""),
                    ),
                    observed_at=timestamp,
                    observed_state=(
                        "stale"
                        if (self._now - timestamp).total_seconds() > 300
                        else "current"
                    ),
                    facts={
                        "metrics_available": True,
                        "stale": (
                            self._now - timestamp
                        ).total_seconds()
                        > 300,
                        "cpu_usage_millicores": (
                            _quantity_cpu_millicores(usage.get("cpu")) or 0
                        ),
                        "memory_usage_bytes": (
                            _quantity_bytes(usage.get("memory")) or 0
                        ),
                        "cpu_limit_percent": None,
                        "memory_limit_percent": None,
                        "consecutive_cpu_over_threshold": 0,
                        "consecutive_memory_over_threshold": 0,
                    },
                )
            )

    def _parse_timestamp(self, value: str | None) -> datetime:
        if not value:
            return self._now
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _aware(parsed) or self._now
        except ValueError:
            return self._now

    def _collect_evidence(
        self,
        request: ProviderCollectionRequest,
        result: ProviderCollectionResult,
    ) -> None:
        pod_targets = [
            item
            for item in request.evidence_targets
            if item.kind.casefold() == "pod"
        ]
        if request.include_logs and len(pod_targets) > request.limits.max_log_pods:
            result.failures.append(
                ProviderCollectionFailure(
                    check_code="pod.runtime",
                    error_code="LOG_POD_LIMIT_EXCEEDED",
                    message=(
                        f"日志巡检目标 {len(pod_targets)} 个 Pod，超过上限 "
                        f"{request.limits.max_log_pods}，请缩小范围"
                    ),
                )
            )
            return
        total_bytes = 0
        for target in request.evidence_targets:
            if request.include_events:
                if target.kind.casefold() == "pod":
                    self._collect_pod_events(target, result)
                elif target.kind.casefold() in {
                    "persistentvolumeclaim",
                    "persistentvolume",
                }:
                    self._collect_storage_events(target, result)
            if request.include_logs and target.kind.casefold() == "pod":
                pod_bytes = self._collect_pod_logs(
                    target,
                    result,
                    remaining_total=max(
                        0,
                        request.limits.max_total_log_bytes - total_bytes,
                    ),
                    max_per_pod=request.limits.max_log_bytes_per_pod,
                    tail_lines=request.limits.max_container_log_lines,
                )
                total_bytes += pod_bytes
                if total_bytes >= request.limits.max_total_log_bytes:
                    break
        result.collected_log_bytes = total_bytes

    def _collect_pod_events(
        self,
        target: ResourceRef,
        result: ProviderCollectionResult,
    ) -> None:
        selector = (
            f"involvedObject.kind=Pod,involvedObject.name={target.name}"
        )
        try:
            events = self._call(
                self.core.list_namespaced_event,
                namespace=target.namespace,
                field_selector=selector,
                _request_timeout=self.timeout,
            ).items
        except Exception as exc:
            self._failure(
                result,
                check_code="pod.runtime",
                exc=exc,
                resource=target,
            )
            return
        warning_window = self._thresholds.warning_event_window_minutes
        current_fault = False
        if any(
            _age_minutes(
                _aware(getattr(event, "event_time", None))
                or _aware(getattr(event, "last_timestamp", None))
                or _aware(getattr(event.metadata, "creation_timestamp", None)),
                self._now,
            )
            > warning_window
            and str(getattr(event, "reason", "") or "")
            in _WARNING_EVENT_REASONS_WITH_CURRENT_FAULT
            for event in events
        ):
            try:
                pod = self._call(
                    self.core.read_namespaced_pod,
                    name=target.name,
                    namespace=target.namespace,
                    _request_timeout=self.timeout,
                )
                conditions = _condition_map(
                    getattr(pod.status, "conditions", None)
                )
                current_fault = (
                    str(getattr(pod.status, "phase", "") or "")
                    not in {"Running", "Succeeded"}
                    or (
                        "Ready" in conditions
                        and not _condition_true(conditions, "Ready")
                    )
                )
            except Exception as exc:
                self._failure(
                    result,
                    check_code="pod.runtime",
                    exc=exc,
                    resource=target,
                )
        warning_reasons: list[str] = []
        probe_failure = False
        volume_failure = False
        for event in events:
            event_type = str(getattr(event, "type", "") or "Unknown")
            reason = str(getattr(event, "reason", "") or "Unknown")
            timestamp = (
                _aware(getattr(event, "event_time", None))
                or _aware(getattr(event, "last_timestamp", None))
                or _aware(getattr(event.metadata, "creation_timestamp", None))
                or self._now
            )
            age_minutes = _age_minutes(timestamp, self._now)
            if event_type != "Warning":
                continue
            if (
                age_minutes > warning_window
                and not (
                    reason in _WARNING_EVENT_REASONS_WITH_CURRENT_FAULT
                    and current_fault
                )
            ):
                continue
            # Message is used transiently for classification only. It can
            # contain application values, so it never enters Evidence.
            message = str(getattr(event, "message", "") or "")
            summary = f"Warning Event: {reason}"
            warning_reasons.append(reason)
            probe_failure = probe_failure or bool(
                _PROBE_REASON_PATTERN.search(message)
            )
            volume_failure = volume_failure or bool(
                _VOLUME_REASON_PATTERN.search(reason + " " + message)
            )
            result.evidence.append(
                Evidence(
                    code="pod_warning_event",
                    source=EvidenceSource.event,
                    summary=summary or reason,
                    facts={
                        "event_type": event_type,
                        "reason": reason,
                        "count": int(getattr(event, "count", 1) or 1),
                        "age_minutes": age_minutes,
                        "probe_failure": probe_failure,
                        "volume_failure": volume_failure,
                    },
                    related_resources=[target],
                    observed_at=timestamp,
                )
            )
            message = ""
        result.observations.append(
            ProviderObservation(
                resource=target,
                observed_at=self._now,
                observed_state="warning_events" if warning_reasons else "no_recent_warning",
                facts={
                    "phase": "Unknown",
                    "warning_reasons": warning_reasons[:50],
                    "probe_failure": probe_failure,
                    "volume_mount_failure": volume_failure,
                    "missing_references": [],
                    "restart_delta": 0,
                },
            )
        )

    def _collect_storage_events(
        self,
        target: ResourceRef,
        result: ProviderCollectionResult,
    ) -> None:
        selector = (
            f"involvedObject.kind={target.kind},"
            f"involvedObject.name={target.name}"
        )
        try:
            if target.namespace:
                events = self._call(
                    self.core.list_namespaced_event,
                    namespace=target.namespace,
                    field_selector=selector,
                    _request_timeout=self.timeout,
                ).items
            else:
                events = self._call(
                    self.core.list_event_for_all_namespaces,
                    field_selector=selector,
                    _request_timeout=self.timeout,
                ).items
        except Exception as exc:
            self._failure(
                result,
                check_code="storage.status",
                exc=exc,
                resource=target,
            )
            return
        warning_window = self._thresholds.warning_event_window_minutes
        for event in events:
            event_type = str(getattr(event, "type", "") or "Unknown")
            timestamp = (
                _aware(getattr(event, "event_time", None))
                or _aware(getattr(event, "last_timestamp", None))
                or _aware(getattr(event.metadata, "creation_timestamp", None))
                or self._now
            )
            age_minutes = _age_minutes(timestamp, self._now)
            if event_type != "Warning" or age_minutes > warning_window:
                continue
            reason = str(getattr(event, "reason", "") or "Unknown")
            result.evidence.append(
                Evidence(
                    code="storage_warning_event",
                    source=EvidenceSource.event,
                    summary=f"Warning Event: {reason}",
                    facts={
                        "event_type": event_type,
                        "reason": reason,
                        "count": int(getattr(event, "count", 1) or 1),
                        "age_minutes": age_minutes,
                    },
                    related_resources=[target],
                    observed_at=timestamp,
                )
            )

    def _collect_pod_logs(
        self,
        target: ResourceRef,
        result: ProviderCollectionResult,
        *,
        remaining_total: int,
        max_per_pod: int,
        tail_lines: int,
    ) -> int:
        try:
            pod = self._call(
                self.core.read_namespaced_pod,
                name=target.name,
                namespace=target.namespace,
                _request_timeout=self.timeout,
            )
        except Exception as exc:
            self._failure(
                result,
                check_code="pod.runtime",
                exc=exc,
                resource=target,
            )
            return 0
        pod_budget = min(max_per_pod, remaining_total)
        if pod_budget <= 0:
            return 0
        collected = 0
        read_any = False
        pod_truncated = False
        containers = list(getattr(pod.spec, "containers", None) or [])
        for container in containers:
            if collected >= pod_budget:
                pod_truncated = True
                break
            try:
                raw = self._call(
                    self.core.read_namespaced_pod_log,
                    name=target.name,
                    namespace=target.namespace,
                    container=container.name,
                    tail_lines=tail_lines,
                    _request_timeout=self.timeout,
                )
            except Exception as exc:
                self._failure(
                    result,
                    check_code="pod.runtime",
                    exc=exc,
                    resource=target,
                )
                continue
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw or "")
            encoded = text.encode("utf-8")
            allowed = max(0, pod_budget - collected)
            truncated = len(encoded) > allowed
            pod_truncated = pod_truncated or truncated
            sample = encoded[:allowed].decode("utf-8", errors="ignore")
            collected += min(len(encoded), allowed)
            read_any = True
            if self.log_matcher and sample:
                result.evidence.extend(
                    self.log_matcher(
                        target,
                        container.name,
                        sample,
                        pod_truncated,
                        self._now,
                    )
                )
            # Drop raw/sample before constructing contract DTOs.
            raw = text = sample = ""
        if read_any:
            result.log_pods_read += 1
            result.evidence.append(
                Evidence(
                    code="pod_log_collection",
                    source=EvidenceSource.derived,
                    summary=(
                        "已按限制读取日志并在内存中完成匹配"
                        + ("，结果已截断" if pod_truncated else "")
                    ),
                    facts={"collected_bytes": collected},
                    related_resources=[target],
                    observed_at=self._now,
                    truncated=pod_truncated,
                )
            )
        return collected

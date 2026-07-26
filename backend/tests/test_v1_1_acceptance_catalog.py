"""Independent fixtures for exact PRD section 14 resource scenarios."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from kubernetes.client.exceptions import ApiException

from app.providers.kubernetes_collection import KubernetesResourceCollector
from app.schemas.v1_1 import (
    CheckStatus,
    CollectionLayer,
    InspectionPolicySettings,
    InspectionScope,
    InspectionTrigger,
    IssueSeverity,
    ProviderCollectionResult,
    ProviderObservation,
    ResourceRef,
)
from app.services.resource_inspection import evaluate_resource_collection


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
SCOPE = InspectionScope(type="namespace", namespace="demo")


def _observation(
    kind: str,
    name: str,
    *,
    state: str | None = None,
    facts: dict | None = None,
    namespace: str | None = "demo",
) -> ProviderObservation:
    return ProviderObservation(
        resource=ResourceRef(kind=kind, namespace=namespace, name=name),
        observed_at=NOW,
        observed_state=state,
        facts=facts or {},
    )


def _evaluate(*observations: ProviderObservation):
    return evaluate_resource_collection(
        ProviderCollectionResult(
            layer=CollectionLayer.status,
            observations=list(observations),
        ),
        scope=SCOPE,
        policy=InspectionPolicySettings(),
        trigger=InspectionTrigger.manual,
        now=NOW,
    )


def _by_code(evaluations, code: str):
    return next(item for item in evaluations if item.coverage.check_code == code)


@pytest.mark.parametrize(
    ("observation", "expected_code", "expected_severity"),
    [
        (
            _observation(
                "Deployment",
                "api",
                facts={
                    "desired": 3,
                    "ready": 1,
                    "available": 1,
                    "updated": 1,
                    "paused": False,
                },
            ),
            "WORKLOAD_REPLICAS_UNAVAILABLE",
            IssueSeverity.warning,
        ),
        (
            _observation(
                "Deployment",
                "api",
                facts={
                    "desired": 3,
                    "ready": 1,
                    "progress_deadline_exceeded": True,
                    "paused": False,
                },
            ),
            "WORKLOAD_ROLLOUT_STALLED",
            IssueSeverity.critical,
        ),
        (
            _observation(
                "StatefulSet",
                "database",
                facts={"desired": 3, "ready": 1},
            ),
            "WORKLOAD_REPLICAS_UNAVAILABLE",
            IssueSeverity.warning,
        ),
        (
            _observation(
                "Job",
                "migration",
                facts={
                    "failed": 1,
                    "failure_condition": True,
                    "deadline_exceeded": False,
                },
            ),
            "JOB_FAILED",
            IssueSeverity.warning,
        ),
    ],
)
def test_prd_workload_failure_catalog(
    observation,
    expected_code,
    expected_severity,
) -> None:
    result = _by_code(_evaluate(observation), "workload.status")

    assert result.coverage.status == CheckStatus.abnormal
    assert [(item.issue_code.value, item.severity) for item in result.issue_candidates] == [
        (expected_code, expected_severity)
    ]


def test_prd_service_selector_matches_no_pods() -> None:
    result = _by_code(
        _evaluate(
            _observation(
                "Service",
                "api",
                facts={
                    "service_type": "ClusterIP",
                    "selector_present": True,
                    "selector": ["app=api"],
                    "selected_pods": 0,
                    "endpoint_slices": 0,
                    "ready_endpoints": 0,
                },
            )
        ),
        "service.endpoints",
    )

    assert {item.issue_code.value for item in result.issue_candidates} == {
        "SERVICE_SELECTOR_MISMATCH",
        "SERVICE_NO_READY_ENDPOINT",
    }


@pytest.mark.parametrize(
    ("facts", "expected_code", "expected_severity"),
    [
        ({"exists": False}, "TLS_SECRET_NOT_FOUND", IssueSeverity.critical),
        (
            {
                "exists": True,
                "parse_ok": True,
                "days_until_expiry": -1,
                "host_match": True,
                "key_match": True,
            },
            "TLS_CERT_EXPIRED",
            IssueSeverity.critical,
        ),
    ],
)
def test_prd_tls_missing_and_expired_catalog(
    facts,
    expected_code,
    expected_severity,
) -> None:
    result = _by_code(
        _evaluate(_observation("TLSSecret", "api-tls", facts=facts)),
        "tls.certificate",
    )

    issue = result.issue_candidates[0]
    assert issue.issue_code.value == expected_code
    assert issue.severity == expected_severity


@pytest.mark.parametrize(
    ("observation", "expected_code", "expected_severity"),
    [
        (
            _observation(
                "PersistentVolumeClaim",
                "data",
                state="Pending",
                facts={
                    "phase": "Pending",
                    "pending_minutes": 10,
                    "volume_binding_mode": "Immediate",
                    "consumer_pods": 1,
                },
            ),
            "PVC_NOT_BOUND",
            IssueSeverity.warning,
        ),
        (
            _observation(
                "PersistentVolume",
                "pv-data",
                namespace=None,
                state="Failed",
                facts={"phase": "Failed"},
            ),
            "PV_FAILED",
            IssueSeverity.critical,
        ),
    ],
)
def test_prd_storage_failure_catalog(
    observation,
    expected_code,
    expected_severity,
) -> None:
    result = _by_code(_evaluate(observation), "storage.status")
    issue = result.issue_candidates[0]

    assert issue.issue_code.value == expected_code
    assert issue.severity == expected_severity


def test_prd_failed_mount_event_is_correlated_to_pod() -> None:
    result = _by_code(
        _evaluate(
            _observation(
                "Pod",
                "api-0",
                state="Pending",
                facts={
                    "phase": "Pending",
                    "ready": False,
                    "warning_reasons": ["FailedMount"],
                    "volume_mount_failure": True,
                },
            )
        ),
        "pod.runtime",
    )

    assert "VOLUME_MOUNT_FAILED" in {
        item.issue_code.value for item in result.issue_candidates
    }
    volume_issue = next(
        item
        for item in result.issue_candidates
        if item.issue_code.value == "VOLUME_MOUNT_FAILED"
    )
    assert volume_issue.evidence[0].source.value == "event"


def test_prd_node_not_ready_after_grace_is_critical() -> None:
    result = _by_code(
        _evaluate(
            _observation(
                "Node",
                "node-a",
                namespace=None,
                facts={
                    "ready_status": "False",
                    "ready_age_seconds": 120,
                    "memory_pressure": False,
                    "disk_pressure": False,
                    "pid_pressure": False,
                    "network_unavailable": False,
                },
            )
        ),
        "node.health",
    )
    issue = result.issue_candidates[0]

    assert issue.issue_code.value == "NODE_NOT_READY"
    assert issue.severity == IssueSeverity.critical


def test_prd_init_image_pull_and_probe_failures_keep_distinct_evidence() -> None:
    result = _by_code(
        _evaluate(
            _observation(
                "Pod",
                "api-0",
                state="Pending",
                facts={
                    "phase": "Pending",
                    "ready": False,
                    "init_failure_reason": "Error",
                    "image_pull_reason": "ImagePullBackOff",
                    "probe_failure": True,
                },
            )
        ),
        "pod.runtime",
    )
    issues = {
        item.issue_code.value: item
        for item in result.issue_candidates
    }

    assert {
        "POD_INIT_CONTAINER_FAILED",
        "POD_IMAGE_PULL_FAILED",
        "POD_PROBE_FAILED",
    } <= set(issues)
    assert issues["POD_INIT_CONTAINER_FAILED"].evidence[0].code == "pod_init_failed"
    assert issues["POD_IMAGE_PULL_FAILED"].evidence[0].code == "pod_image_pull"
    assert issues["POD_PROBE_FAILED"].evidence[0].code == "pod_probe_failed"


def test_prd_all_missing_pod_reference_types_remain_visible() -> None:
    missing = [
        "ConfigMap/app-config",
        "Secret/app-secret",
        "ServiceAccount/runtime",
        "Secret/image-pull",
        "PersistentVolumeClaim/data",
    ]
    result = _by_code(
        _evaluate(
            _observation(
                "Pod",
                "api-0",
                state="Pending",
                facts={
                    "phase": "Pending",
                    "ready": False,
                    "missing_references": missing,
                },
            )
        ),
        "pod.runtime",
    )
    issue = next(
        item
        for item in result.issue_candidates
        if item.issue_code.value == "POD_CONFIG_REFERENCE_MISSING"
    )

    assert issue.evidence[0].facts["missing_references"] == missing


def test_prd_provider_checks_all_pod_reference_types_with_targeted_gets() -> None:
    def missing(**_kwargs):
        raise ApiException(status=404, reason="Not Found")

    core = SimpleNamespace(
        read_namespaced_config_map=missing,
        read_namespaced_secret=missing,
        read_namespaced_service_account=missing,
        read_namespaced_persistent_volume_claim=missing,
    )
    collector = KubernetesResourceCollector(
        settings=SimpleNamespace(k8s_request_timeout=5),
        core=core,
        apps=SimpleNamespace(),
        batch=SimpleNamespace(),
        networking=SimpleNamespace(),
        discovery=SimpleNamespace(),
        storage=SimpleNamespace(),
        custom=SimpleNamespace(),
        version_api=SimpleNamespace(),
    )
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="api-0",
            namespace="demo",
            uid="pod-1",
        ),
        spec=SimpleNamespace(
            service_account_name="runtime",
            image_pull_secrets=[SimpleNamespace(name="registry")],
            containers=[
                SimpleNamespace(
                    env_from=[
                        SimpleNamespace(
                            config_map_ref=SimpleNamespace(
                                name="app-config",
                                optional=False,
                            ),
                            secret_ref=SimpleNamespace(
                                name="app-secret",
                                optional=False,
                            ),
                        )
                    ],
                    env=[],
                )
            ],
            init_containers=[],
            volumes=[
                SimpleNamespace(
                    config_map=None,
                    secret=None,
                    projected=None,
                    persistent_volume_claim=SimpleNamespace(
                        claim_name="data"
                    ),
                )
            ],
        ),
    )

    missing_references = collector._missing_pod_references(
        pod,
        ProviderCollectionResult(layer=CollectionLayer.status),
    )

    assert missing_references == [
        "ConfigMap/app-config",
        "Secret/app-secret",
        "Secret/registry",
        "ServiceAccount/runtime",
        "PersistentVolumeClaim/data",
    ]


def test_prd_job_without_deadline_is_info_not_failed() -> None:
    result = _by_code(
        _evaluate(
            _observation(
                "Job",
                "long-running",
                facts={
                    "failed": 0,
                    "failure_condition": False,
                    "deadline_exceeded": False,
                    "completion_condition": False,
                    "active_deadline_seconds": None,
                    "age_minutes": 121,
                },
            )
        ),
        "workload.status",
    )
    issue = result.issue_candidates[0]

    assert issue.issue_code.value == "JOB_FAILED"
    assert issue.severity == IssueSeverity.info
    assert "不判定失败" in issue.reason

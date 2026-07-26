from datetime import datetime, timezone

from app.schemas.v1_1 import (
    CheckStatus,
    CollectionLayer,
    InspectionPolicySettings,
    InspectionScope,
    InspectionThresholds,
    InspectionTrigger,
    ProviderCollectionFailure,
    ProviderCollectionRequest,
    ProviderCollectionResult,
    ProviderObservation,
    RequiredComponentPolicy,
    ResourceRef,
    build_inspection_scope_key,
)
from app.providers.mock_provider import MockInspectionProvider
from app.services.resource_inspection import evaluate_resource_collection


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
SCOPE = InspectionScope(type="namespace", namespace="demo")


def observation(
    kind: str,
    name: str,
    *,
    namespace: str | None = "demo",
    state: str | None = None,
    facts: dict | None = None,
    related: list[ResourceRef] | None = None,
) -> ProviderObservation:
    return ProviderObservation(
        resource=ResourceRef(kind=kind, namespace=namespace, name=name),
        observed_at=NOW,
        observed_state=state,
        facts=facts or {},
        related_resources=related or [],
    )


def evaluate(
    observations: list[ProviderObservation],
    *,
    failures: list[ProviderCollectionFailure] | None = None,
    policy: InspectionPolicySettings | None = None,
    trigger: InspectionTrigger = InspectionTrigger.manual,
):
    return evaluate_resource_collection(
        ProviderCollectionResult(
            layer=CollectionLayer.status,
            observations=observations,
            failures=failures or [],
        ),
        scope=SCOPE,
        policy=policy or InspectionPolicySettings(),
        trigger=trigger,
        now=NOW,
    )


def by_code(evaluations, code: str):
    return next(item for item in evaluations if item.coverage.check_code == code)


def test_every_evaluation_uses_real_scope_and_public_scope_key_builder() -> None:
    evaluations = evaluate([])

    assert evaluations
    assert all(item.scope == SCOPE for item in evaluations)
    assert all(item.scope_key == build_inspection_scope_key(SCOPE) for item in evaluations)
    assert all(item.coverage.issue_count == len(item.issue_candidates) for item in evaluations)


def test_running_but_not_ready_pod_and_init_failure_are_abnormal() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Pod",
                    "api-0",
                    state="Running",
                    facts={
                        "ready": False,
                        "init_failure_reason": "Error",
                        "phase": "Running",
                    },
                )
            ]
        ),
        "pod.runtime",
    )

    assert result.coverage.status == CheckStatus.abnormal
    assert {issue.issue_code.value for issue in result.issue_candidates} == {
        "POD_NOT_READY",
        "POD_INIT_CONTAINER_FAILED",
    }


def test_completed_pod_and_zero_replica_or_paused_workload_do_not_alert() -> None:
    evaluations = evaluate(
        [
            observation("Pod", "migrate", state="Succeeded", facts={"phase": "Succeeded", "ready": False}),
            observation(
                "Deployment",
                "scaled-down",
                facts={"desired": 0, "ready": 0, "available": 0, "updated": 0, "paused": False},
            ),
            observation(
                "Deployment",
                "paused",
                facts={"desired": 3, "ready": 0, "available": 0, "updated": 0, "paused": True},
            ),
            observation("CronJob", "nightly", facts={"suspended": True}),
        ]
    )

    assert by_code(evaluations, "pod.runtime").coverage.status == CheckStatus.passed
    assert by_code(evaluations, "workload.status").coverage.status == CheckStatus.passed


def test_service_without_ready_endpoint_alerts_and_external_name_skips() -> None:
    evaluations = evaluate(
        [
            observation(
                "Service",
                "api",
                facts={
                    "service_type": "ClusterIP",
                    "selector_present": True,
                    "selected_pods": 2,
                    "ready_endpoints": 0,
                    "ingress_referenced": True,
                },
            ),
            observation(
                "Service",
                "external",
                facts={"service_type": "ExternalName", "selector_present": False},
            ),
        ]
    )
    result = by_code(evaluations, "service.endpoints")

    assert result.coverage.status == CheckStatus.abnormal
    assert result.issue_candidates[0].issue_code.value == "SERVICE_NO_READY_ENDPOINT"
    assert result.issue_candidates[0].severity.value == "critical"


def test_service_selector_mismatch_is_not_inferred_for_selectorless_service() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Service",
                    "manual-endpoints",
                    facts={
                        "service_type": "ClusterIP",
                        "selector_present": False,
                        "endpoint_slices": 1,
                        "ready_endpoints": 1,
                    },
                )
            ]
        ),
        "service.endpoints",
    )

    assert result.coverage.status == CheckStatus.passed


def test_unused_selectorless_service_without_manual_endpoints_is_skipped() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Service",
                    "manual-empty",
                    facts={
                        "service_type": "ClusterIP",
                        "selector_present": False,
                        "endpoint_slices": 0,
                        "ready_endpoints": 0,
                        "ingress_referenced": False,
                    },
                )
            ]
        ),
        "service.endpoints",
    )

    assert result.coverage.status == CheckStatus.skipped


def test_ingress_referenced_selectorless_service_without_endpoint_is_critical() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Service",
                    "manual-empty",
                    facts={
                        "service_type": "ClusterIP",
                        "selector_present": False,
                        "endpoint_slices": 0,
                        "ready_endpoints": 0,
                        "ingress_referenced": True,
                    },
                )
            ]
        ),
        "service.endpoints",
    )

    assert result.coverage.status == CheckStatus.abnormal
    assert result.issue_candidates[0].severity.value == "critical"


def test_ingress_resource_backend_is_skipped_not_service_missing() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Ingress",
                    "assets",
                    facts={"resource_backends": 1, "service_backends": 0},
                )
            ]
        ),
        "ingress.config_chain",
    )

    assert result.coverage.status == CheckStatus.skipped
    assert result.issue_candidates == []


def test_ingress_backend_and_class_failures_are_reported_without_claiming_connectivity() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Ingress",
                    "api",
                    facts={
                        "service_backends": 1,
                        "missing_backend_services": ["missing"],
                        "invalid_backend_ports": ["api:8443"],
                        "missing_ingress_class": "missing-class",
                    },
                )
            ]
        ),
        "ingress.config_chain",
    )

    assert result.coverage.status == CheckStatus.abnormal
    assert {item.issue_code.value for item in result.issue_candidates} == {
        "INGRESS_BACKEND_NOT_FOUND",
        "INGRESS_BACKEND_PORT_INVALID",
        "INGRESS_CLASS_NOT_FOUND",
    }
    assert all("访问正常" not in item.summary for item in result.issue_candidates)


def test_tls_expiring_host_mismatch_and_key_mismatch_are_independent() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "TLSSecret",
                    "api-tls",
                    facts={
                        "exists": True,
                        "parse_ok": True,
                        "days_until_expiry": 5,
                        "host_match": False,
                        "key_match": False,
                        "hosts": ["api.example.com"],
                    },
                )
            ]
        ),
        "tls.certificate",
    )

    assert {item.issue_code.value for item in result.issue_candidates} == {
        "TLS_CERT_EXPIRING",
        "TLS_HOST_MISMATCH",
        "TLS_KEY_MISMATCH",
    }
    assert all("tls_key" not in evidence.facts for item in result.issue_candidates for evidence in item.evidence)


def test_wait_for_first_consumer_without_consumer_is_expected() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "PersistentVolumeClaim",
                    "data",
                    state="Pending",
                    facts={
                        "phase": "Pending",
                        "pending_minutes": 60,
                        "volume_binding_mode": "WaitForFirstConsumer",
                        "consumer_pods": 0,
                    },
                )
            ]
        ),
        "storage.status",
    )

    assert result.coverage.status == CheckStatus.passed


def test_retain_released_pv_is_info_not_storage_failure() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "PersistentVolume",
                    "pv-data",
                    namespace=None,
                    state="Released",
                    facts={
                        "phase": "Released",
                        "released_hours": 48,
                        "reclaim_policy": "Retain",
                    },
                )
            ]
        ),
        "storage.status",
    )

    assert result.coverage.status == CheckStatus.abnormal
    assert result.issue_candidates[0].issue_code.value == "PV_RELEASED_STALE"
    assert result.issue_candidates[0].severity.value == "info"


def test_node_cordon_and_taint_alone_do_not_alert_but_pressure_does() -> None:
    result = by_code(
        evaluate(
            [
                observation(
                    "Node",
                    "node-a",
                    namespace=None,
                    facts={
                        "ready_status": "True",
                        "unschedulable": True,
                        "taints": ["dedicated=gpu:NoSchedule"],
                        "memory_pressure": False,
                        "disk_pressure": True,
                        "pid_pressure": False,
                        "network_unavailable": False,
                    },
                )
            ]
        ),
        "node.health",
    )

    assert [item.issue_code.value for item in result.issue_candidates] == ["NODE_DISK_PRESSURE"]


def test_node_not_ready_grace_uses_policy_without_hiding_pressure() -> None:
    policy = InspectionPolicySettings(
        thresholds=InspectionThresholds(
            node_not_ready_grace_seconds=60,
        )
    )
    result = by_code(
        evaluate(
            [
                observation(
                    "Node",
                    "node-a",
                    namespace=None,
                    facts={
                        "ready_status": "False",
                        "ready_age_seconds": 30,
                        "memory_pressure": False,
                        "disk_pressure": False,
                        "pid_pressure": False,
                        "network_unavailable": False,
                    },
                )
            ],
            policy=policy,
        ),
        "node.health",
    )

    assert result.coverage.status == CheckStatus.passed


def test_metrics_unavailable_is_skipped_and_missing_limit_never_alerts() -> None:
    skipped = by_code(evaluate([]), "metrics.resource")
    assert skipped.coverage.status == CheckStatus.skipped

    result = by_code(
        evaluate(
            [
                observation(
                    "PodMetric",
                    "api-0",
                    facts={
                        "metrics_available": True,
                        "stale": False,
                        "memory_limit_bytes": None,
                        "memory_usage_bytes": 10_000_000,
                        "memory_limit_percent": None,
                        "consecutive_over_threshold": 99,
                    },
                )
            ],
            trigger=InspectionTrigger.scheduled,
        ),
        "metrics.resource",
    )
    assert result.coverage.status == CheckStatus.passed


def test_metrics_alert_requires_three_scheduled_cycles() -> None:
    policy = InspectionPolicySettings(
        thresholds=InspectionThresholds(resource_usage_consecutive_cycles=3),
    )
    item = observation(
        "PodMetric",
        "api-0",
        facts={
            "metrics_available": True,
            "stale": False,
            "memory_limit_percent": 95.0,
            "consecutive_over_threshold": 3,
        },
    )

    manual = by_code(evaluate([item], policy=policy), "metrics.resource")
    scheduled = by_code(
        evaluate([item], policy=policy, trigger=InspectionTrigger.scheduled),
        "metrics.resource",
    )

    assert manual.coverage.status == CheckStatus.passed
    assert scheduled.issue_candidates[0].issue_code.value == "RESOURCE_USAGE_HIGH"


def test_api_failure_produces_failed_coverage_without_fake_issues() -> None:
    failure = ProviderCollectionFailure(
        check_code="service.endpoints",
        error_code="KUBERNETES_API_FORBIDDEN",
        message="无权读取 EndpointSlice",
    )
    result = by_code(evaluate([], failures=[failure]), "service.endpoints")

    assert result.coverage.status == CheckStatus.failed
    assert result.issue_candidates == []


def test_required_component_policy_only_alerts_for_configured_component() -> None:
    policy = InspectionPolicySettings(
        required_components=[
            RequiredComponentPolicy(
                name="ingress controller",
                namespace="ingress-nginx",
                kind="Deployment",
                label_selector="app.kubernetes.io/name=ingress-nginx",
            )
        ]
    )
    result = by_code(evaluate([], policy=policy), "required_components")

    assert result.coverage.status == CheckStatus.abnormal
    assert result.issue_candidates[0].issue_code.value == "REQUIRED_COMPONENT_MISSING"


def test_required_component_supports_kubernetes_set_and_exists_selectors() -> None:
    policy = InspectionPolicySettings(
        required_components=[
            RequiredComponentPolicy(
                name="ingress controller",
                namespace="demo",
                kind="Deployment",
                label_selector=(
                    "app.kubernetes.io/name in (ingress-nginx,traefik),"
                    "app.kubernetes.io/managed-by"
                ),
            )
        ]
    )
    result = by_code(
        evaluate(
            [
                observation(
                    "Deployment",
                    "controller",
                    facts={
                        "desired": 1,
                        "ready": 1,
                        "labels": [
                            "app.kubernetes.io/name=ingress-nginx",
                            "app.kubernetes.io/managed-by=Helm",
                        ],
                    },
                )
            ],
            policy=policy,
        ),
        "required_components",
    )

    assert result.coverage.status == CheckStatus.passed


def test_mock_provider_exposes_passed_abnormal_skipped_and_failed_states() -> None:
    provider = MockInspectionProvider()
    request = ProviderCollectionRequest(
        scope=SCOPE,
        layer=CollectionLayer.status,
        trigger=InspectionTrigger.manual,
    )

    evaluations = evaluate_resource_collection(
        provider.collect_resources(request),
        scope=SCOPE,
        policy=InspectionPolicySettings(),
        trigger=InspectionTrigger.manual,
        now=NOW,
    )

    statuses = {item.coverage.status for item in evaluations}
    assert {
        CheckStatus.passed,
        CheckStatus.abnormal,
        CheckStatus.skipped,
        CheckStatus.failed,
    } <= statuses


def test_cluster_collection_keeps_namespace_failures_and_recovery_scopes_isolated() -> None:
    cluster_scope = InspectionScope(type="cluster")
    collection = ProviderCollectionResult(
        layer=CollectionLayer.status,
        observations=[
            observation(
                "Pod",
                "demo-api-0",
                namespace="demo",
                state="Running",
                facts={"phase": "Running", "ready": False},
            ),
            observation(
                "Pod",
                "prod-api-0",
                namespace="prod",
                state="Running",
                facts={"phase": "Running", "ready": True},
            ),
        ],
        failures=[
            ProviderCollectionFailure(
                check_code="service.endpoints",
                error_code="KUBERNETES_API_403",
                message="prod Service API 无权限",
                resource=ResourceRef(kind="Namespace", name="prod"),
            )
        ],
    )

    evaluations = evaluate_resource_collection(
        collection,
        scope=cluster_scope,
        policy=InspectionPolicySettings(),
        trigger=InspectionTrigger.scheduled,
        now=NOW,
    )
    demo_pod = next(
        item
        for item in evaluations
        if item.scope.namespace == "demo"
        and item.coverage.check_code == "pod.runtime"
    )
    prod_pod = next(
        item
        for item in evaluations
        if item.scope.namespace == "prod"
        and item.coverage.check_code == "pod.runtime"
    )
    prod_service = next(
        item
        for item in evaluations
        if item.scope.namespace == "prod"
        and item.coverage.check_code == "service.endpoints"
    )

    assert demo_pod.coverage.status == CheckStatus.abnormal
    assert prod_pod.coverage.status == CheckStatus.passed
    assert prod_service.coverage.status == CheckStatus.failed
    assert demo_pod.scope_key != prod_pod.scope_key

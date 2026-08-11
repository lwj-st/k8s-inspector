from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone

import pytest
from kubernetes.client.exceptions import ApiException

from app.providers.base import LogPodLimitExceededError, TemporaryPodLogCollection
from app.providers.kubernetes_provider import KubernetesInspectionProvider
from app.providers.mock_provider import MockInspectionProvider
from app.schemas.v1_1 import CollectionLimits


def _make_provider() -> KubernetesInspectionProvider:
    provider = KubernetesInspectionProvider.__new__(KubernetesInspectionProvider)
    provider.settings = SimpleNamespace(k8s_request_timeout=5, k8s_log_tail_lines=1000, k8s_log_summary_lines=5)
    provider.core = SimpleNamespace()
    provider.apps = SimpleNamespace()
    provider.batch = SimpleNamespace()
    provider.networking = SimpleNamespace()
    provider.discovery = SimpleNamespace()
    provider.storage = SimpleNamespace()
    provider.custom = SimpleNamespace()
    provider.version_api = SimpleNamespace()
    return provider


def test_collect_diagnosis_context_filters_pods_by_scope() -> None:
    provider = _make_provider()
    provider.run_namespace_inspection = lambda namespace, label_selector: {
        "namespace": namespace,
        "label_selector": label_selector,
        "health_status": "warning",
        "executed_at": "2026-07-06T00:00:00Z",
        "pods": [
            {"name": "demo-api-abc", "status": "CrashLoopBackOff", "restarts": 3, "log_summary": "database connection refused"},
            {"name": "demo-worker-xyz", "status": "Running", "restarts": 0, "log_summary": None},
        ],
        "services": [{"name": "demo-api", "status": "healthy", "summary": "ClusterIP"}],
        "ingresses": [],
        "tls_secrets": [],
        "daemonsets": [],
    }

    context = provider.collect_diagnosis_context("demo", "pod/demo-api-abc")

    assert [pod["name"] for pod in context["pods"]] == ["demo-api-abc"]
    assert context["related_objects"]["services"][0]["name"] == "demo-api"


def test_collect_diagnosis_context_keeps_matching_pods_for_workload_scope() -> None:
    provider = _make_provider()
    provider.run_namespace_inspection = lambda namespace, label_selector: {
        "namespace": namespace,
        "label_selector": label_selector,
        "health_status": "warning",
        "executed_at": "2026-07-06T00:00:00Z",
        "pods": [
            {"name": "demo-api-abc", "status": "CrashLoopBackOff", "restarts": 3, "log_summary": "database connection refused"},
            {"name": "demo-api-def", "status": "Running", "restarts": 0, "log_summary": None},
            {"name": "demo-worker-xyz", "status": "Running", "restarts": 0, "log_summary": None},
        ],
        "services": [],
        "ingresses": [],
        "tls_secrets": [],
        "daemonsets": [],
    }

    context = provider.collect_diagnosis_context("demo", "deployment/demo-api")

    assert [pod["name"] for pod in context["pods"]] == ["demo-api-abc", "demo-api-def"]


def test_run_pod_inspection_reads_single_pod_directly() -> None:
    provider = _make_provider()
    provider.run_namespace_inspection = lambda namespace, label_selector: (_ for _ in ()).throw(
        AssertionError("run_namespace_inspection should not be used for single pod inspection")
    )
    provider.core.read_namespaced_pod = lambda name, namespace, _request_timeout: SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=namespace, labels={"app": "demo-api"}),
        spec=SimpleNamespace(
            node_name="node-a",
            containers=[SimpleNamespace(name="demo-api")],
        ),
        status=SimpleNamespace(
            phase="Running",
            conditions=[SimpleNamespace(type="Ready", status="True")],
            container_statuses=[
                SimpleNamespace(
                    name="demo-api",
                    restart_count=0,
                    state=SimpleNamespace(waiting=None, running=SimpleNamespace(), terminated=None),
                )
            ],
        ),
    )
    provider.core.list_namespaced_service = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.networking.list_namespaced_ingress = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.apps.list_namespaced_daemon_set = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_secret = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_event = lambda namespace, field_selector, _request_timeout: SimpleNamespace(items=[])
    provider.core.read_namespaced_pod_log = lambda **kwargs: ""

    result = provider.run_pod_inspection("demo", "demo-api-abc")

    assert result["pod"]["name"] == "demo-api-abc"
    assert result["inspection_target"]["type"] == "pod"


def test_pod_resource_usage_is_built_from_metrics_api() -> None:
    provider = _make_provider()
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="demo-api-abc"),
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(
                    resources=SimpleNamespace(
                        requests={"cpu": "100m", "memory": "128Mi"},
                        limits={"cpu": "500m", "memory": "512Mi"},
                    )
                )
            ],
            init_containers=[],
            overhead={},
        ),
    )
    provider.custom.list_namespaced_custom_object = lambda **kwargs: {
        "items": [
            {
                "metadata": {"name": "demo-api-abc"},
                "timestamp": "2026-07-29T01:36:43Z",
                "containers": [
                    {"usage": {"cpu": "250m", "memory": "256Mi"}},
                    {"usage": {"cpu": "50000000n", "memory": "64Mi"}},
                ],
            }
        ]
    }

    usage = provider._pod_resource_usage_map("demo", [pod])["demo-api-abc"]

    assert usage == {
        "cpu": "300m",
        "memory": "320Mi",
        "sample_time": "2026-07-29T01:36:43Z",
        "cpu_request_percent": "300.0%",
        "memory_request_percent": "250.0%",
        "cpu_limit_percent": "60.0%",
        "memory_limit_percent": "62.5%",
    }


def test_run_pod_inspection_reads_logs_for_every_container_even_when_pod_is_running() -> None:
    provider = _make_provider()
    provider.run_namespace_inspection = lambda namespace, label_selector: (_ for _ in ()).throw(
        AssertionError("run_namespace_inspection should not be used for single pod inspection")
    )
    provider.core.read_namespaced_pod = lambda name, namespace, _request_timeout: SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=namespace, labels={"app": "demo-api"}),
        spec=SimpleNamespace(
            node_name="node-a",
            containers=[SimpleNamespace(name="demo-api"), SimpleNamespace(name="sidecar")],
        ),
        status=SimpleNamespace(
            phase="Running",
            conditions=[SimpleNamespace(type="Ready", status="True")],
            container_statuses=[
                SimpleNamespace(
                    name="demo-api",
                    restart_count=0,
                    state=SimpleNamespace(waiting=None, running=SimpleNamespace(), terminated=None),
                ),
                SimpleNamespace(
                    name="sidecar",
                    restart_count=0,
                    state=SimpleNamespace(waiting=None, running=SimpleNamespace(), terminated=None),
                ),
            ],
        ),
    )
    provider.core.list_namespaced_service = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.networking.list_namespaced_ingress = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.apps.list_namespaced_daemon_set = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_secret = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_event = lambda namespace, field_selector, _request_timeout: SimpleNamespace(items=[])
    log_calls: list[dict] = []

    def read_log(**kwargs):
        log_calls.append(kwargs)
        return f"{kwargs['container']}-line1\n{kwargs['container']}-line2\n{kwargs['container']}-line3\n{kwargs['container']}-line4\n{kwargs['container']}-line5\n{kwargs['container']}-line6"

    provider.core.read_namespaced_pod_log = read_log

    result = provider.run_pod_inspection("demo", "demo-api-abc")

    assert log_calls == [
        {
            "name": "demo-api-abc",
            "namespace": "demo",
            "container": "demo-api",
            "tail_lines": 1000,
            "_request_timeout": 5,
        },
        {
            "name": "demo-api-abc",
            "namespace": "demo",
            "container": "sidecar",
            "tail_lines": 1000,
            "_request_timeout": 5,
        },
    ]
    assert result["pod"]["status"] == "Running"
    assert result["pod"]["container_log_summaries"] == {
        "demo-api": "demo-api-line1\ndemo-api-line2\ndemo-api-line3\ndemo-api-line4\ndemo-api-line5",
        "sidecar": "sidecar-line1\nsidecar-line2\nsidecar-line3\nsidecar-line4\nsidecar-line5",
    }
    assert result["pod"]["log_summary"] == (
        "[demo-api]\n"
        "demo-api-line1\n"
        "demo-api-line2\n"
        "demo-api-line3\n"
        "demo-api-line4\n"
        "demo-api-line5\n"
        "[sidecar]\n"
        "sidecar-line1\n"
        "sidecar-line2\n"
        "sidecar-line3\n"
        "sidecar-line4\n"
        "sidecar-line5"
    )


def test_log_summary_decodes_stringified_bytes_repr() -> None:
    provider = _make_provider()

    assert provider._summarize_log_text('b"line1\\nError: connect ECONNREFUSED\\nline3"') == (
        "line1\n"
        "Error: connect ECONNREFUSED\n"
        "line3"
    )


def _configure_direct_pod_inspection(provider: KubernetesInspectionProvider, pod_status: SimpleNamespace) -> None:
    provider.core.read_namespaced_pod = lambda name, namespace, _request_timeout: SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=namespace, labels={}),
        spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="worker")]),
        status=pod_status,
    )
    provider.core.list_namespaced_service = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.networking.list_namespaced_ingress = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.apps.list_namespaced_daemon_set = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_secret = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider.core.list_namespaced_event = lambda namespace, field_selector, _request_timeout: SimpleNamespace(items=[])
    provider.core.read_namespaced_pod_log = lambda **kwargs: ""


def test_run_pod_inspection_treats_succeeded_completed_as_healthy() -> None:
    provider = _make_provider()
    _configure_direct_pod_inspection(
        provider,
        SimpleNamespace(
            phase="Succeeded",
            container_statuses=[
                SimpleNamespace(
                    name="worker",
                    restart_count=0,
                    state=SimpleNamespace(
                        waiting=None,
                        running=None,
                        terminated=SimpleNamespace(reason="Completed", exit_code=0),
                    ),
                )
            ],
        ),
    )

    result = provider.run_pod_inspection("demo", "safeapi-migrate")

    assert result["health_status"] == "healthy"


def test_run_pod_inspection_keeps_failed_pod_as_warning() -> None:
    provider = _make_provider()
    _configure_direct_pod_inspection(
        provider,
        SimpleNamespace(phase="Failed", container_statuses=[]),
    )

    result = provider.run_pod_inspection("demo", "failed-pod")

    assert result["health_status"] == "warning"


def test_get_overview_ignores_succeeded_completed_pod() -> None:
    provider = _make_provider()
    provider._target_namespaces_for_cluster = lambda: ["migration"]
    provider.core.list_node = lambda _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="node-a"),
                status=SimpleNamespace(conditions=[SimpleNamespace(type="Ready", status="True")]),
            )
        ]
    )
    provider.core.list_namespaced_pod = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="safeapi-migrate", namespace="migration", owner_references=[]),
                spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="worker")]),
                status=SimpleNamespace(
                    phase="Succeeded",
                    container_statuses=[
                        SimpleNamespace(
                            restart_count=0,
                            state=SimpleNamespace(
                                waiting=None,
                                running=None,
                                terminated=SimpleNamespace(reason="Completed", exit_code=0),
                            ),
                        )
                    ],
                ),
            )
        ]
    )
    provider.core.read_namespaced_pod_log = lambda **kwargs: ""

    result = provider.get_overview()

    assert result["issues"] == []
    assert result["health_status"] == "healthy"


def test_list_namespaces_returns_namespace_summaries() -> None:
    provider = _make_provider()
    provider.core.list_namespace = lambda _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="demo", labels={"team": "platform"}),
            ),
            SimpleNamespace(
                metadata=SimpleNamespace(name="prod", labels=None),
            ),
        ]
    )
    provider.core.list_namespaced_pod = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(status=SimpleNamespace(phase="Running")),
            SimpleNamespace(
                status=SimpleNamespace(
                    phase="Pending" if namespace == "demo" else "Running",
                    container_statuses=[],
                )
            ),
        ]
    )

    result = provider.list_namespaces()

    assert result["namespaces"][0]["name"] == "demo"
    assert result["namespaces"][0]["status"] == "warning"
    assert result["namespaces"][0]["pod_count"] == 2
    assert result["namespaces"][0]["abnormal_pod_count"] == 1
    assert result["namespaces"][0]["labels"] == {"team": "platform"}
    assert result["namespaces"][0]["abnormal_categories"] == ["pod_status"]
    assert result["namespaces"][1]["name"] == "prod"


def test_succeeded_completed_pod_is_not_abnormal() -> None:
    provider = _make_provider()
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="safeapi-migrate", owner_references=[]),
        status=SimpleNamespace(
            phase="Succeeded",
            container_statuses=[
                SimpleNamespace(
                    state=SimpleNamespace(
                        waiting=None,
                        running=None,
                        terminated=SimpleNamespace(reason="Completed", exit_code=0),
                    )
                )
            ],
        ),
    )

    assert provider._is_abnormal_pod(pod) is False


def test_provider_keeps_failed_and_container_failures_abnormal() -> None:
    provider = _make_provider()

    failed_pod = SimpleNamespace(
        status=SimpleNamespace(phase="Failed", container_statuses=[]),
        metadata=SimpleNamespace(owner_references=[]),
    )
    crashloop_pod = SimpleNamespace(
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[
                SimpleNamespace(
                    state=SimpleNamespace(
                        waiting=SimpleNamespace(reason="CrashLoopBackOff"),
                        running=None,
                        terminated=None,
                    )
                )
            ],
        ),
        metadata=SimpleNamespace(owner_references=[]),
    )
    error_pod = SimpleNamespace(
        status=SimpleNamespace(
            phase="Succeeded",
            container_statuses=[
                SimpleNamespace(
                    state=SimpleNamespace(
                        waiting=None,
                        running=None,
                        terminated=SimpleNamespace(reason="Error", exit_code=1),
                    )
                )
            ],
        ),
        metadata=SimpleNamespace(owner_references=[]),
    )
    non_zero_completed_pod = SimpleNamespace(
        status=SimpleNamespace(
            phase="Succeeded",
            container_statuses=[
                SimpleNamespace(
                    state=SimpleNamespace(
                        waiting=None,
                        running=None,
                        terminated=SimpleNamespace(reason="Completed", exit_code=1),
                    )
                )
            ],
        ),
        metadata=SimpleNamespace(owner_references=[]),
    )

    assert provider._is_abnormal_pod(failed_pod) is True
    assert provider._is_abnormal_pod(crashloop_pod) is True
    assert provider._is_abnormal_pod(error_pod) is True
    assert provider._is_abnormal_pod(non_zero_completed_pod) is True


def test_list_namespaces_does_not_count_succeeded_completed_pod_as_abnormal() -> None:
    provider = _make_provider()
    provider.core.list_namespace = lambda _request_timeout: SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="migration", labels={}))]
    )
    provider.core.list_namespaced_pod = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="safeapi-migrate", owner_references=[]),
                status=SimpleNamespace(
                    phase="Succeeded",
                    container_statuses=[
                        SimpleNamespace(
                            state=SimpleNamespace(
                                waiting=None,
                                running=None,
                                terminated=SimpleNamespace(reason="Completed", exit_code=0),
                            )
                        )
                    ],
                ),
            )
        ]
    )

    result = provider.list_namespaces()

    assert result["namespaces"][0]["abnormal_pod_count"] == 0
    assert result["namespaces"][0]["status"] == "healthy"
    assert result["namespaces"][0]["abnormal_categories"] == []


def _configure_namespace_inspection_provider(
    provider: KubernetesInspectionProvider,
    *,
    ingress_load_balancer: object | None,
    daemonset_unavailable: int,
) -> None:
    provider.core.list_namespaced_pod = lambda namespace, label_selector, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="demo-api-0",
                    namespace=namespace,
                    uid="pod-1",
                    labels={"app": "demo-api"},
                )
            )
        ]
    )
    provider.core.list_namespaced_service = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="demo-api",
                    namespace=namespace,
                    uid="service-1",
                ),
                spec=SimpleNamespace(
                    type="ClusterIP",
                    selector={"app": "demo-api"},
                    ports=[],
                    cluster_ip="10.0.0.1",
                ),
            )
        ]
    )
    provider.networking.list_namespaced_ingress = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="demo",
                    namespace=namespace,
                    uid="ingress-1",
                ),
                status=SimpleNamespace(load_balancer=ingress_load_balancer),
                spec=SimpleNamespace(
                    rules=[],
                    default_backend=None,
                    ingress_class_name=None,
                    tls=[],
                ),
            )
        ]
    )
    provider.networking.list_ingress_class = lambda _request_timeout: SimpleNamespace(items=[])
    provider.discovery.list_namespaced_endpoint_slice = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    name="demo-api-1",
                    namespace=namespace,
                    labels={"kubernetes.io/service-name": "demo-api"},
                ),
                endpoints=[
                    SimpleNamespace(
                        conditions=SimpleNamespace(ready=True),
                        target_ref=None,
                    )
                ],
            )
        ]
    )
    provider.apps.list_namespaced_daemon_set = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="agent"),
                status=SimpleNamespace(number_unavailable=daemonset_unavailable, desired_number_scheduled=1),
            )
        ]
    )
    provider.core.list_namespaced_secret = lambda namespace, _request_timeout: SimpleNamespace(items=[])
    provider._build_pod_result = lambda namespace, pod, services, **kwargs: {
        "name": "demo-api-1",
        "status": "Running",
        "node_name": "node-a",
        "restarts": 0,
        "containers": [{"name": "demo-api", "restart_count": 0, "state": "running", "reason": None}],
        "events": [],
        "describe_summary": "healthy",
        "log_summary": None,
        "previous_log_summary": None,
        "resource_usage": {},
        "related_resources": [],
    }


def test_run_namespace_inspection_does_not_use_load_balancer_as_health_signal() -> None:
    provider = _make_provider()
    _configure_namespace_inspection_provider(
        provider,
        ingress_load_balancer=None,
        daemonset_unavailable=0,
    )

    result = provider.run_namespace_inspection("demo", None)

    assert result["pods"][0]["status"] == "Running"
    assert result["ingresses"][0]["status"] == "healthy"
    assert result["health_status"] == "healthy"


def test_run_namespace_inspection_warns_when_daemonset_is_degraded() -> None:
    provider = _make_provider()
    _configure_namespace_inspection_provider(
        provider,
        ingress_load_balancer=SimpleNamespace(ingress=[]),
        daemonset_unavailable=1,
    )

    result = provider.run_namespace_inspection("demo", None)

    assert result["pods"][0]["status"] == "Running"
    assert result["daemonsets"][0]["status"] == "degraded"
    assert result["health_status"] == "warning"


def test_run_namespace_inspection_is_healthy_when_all_resources_are_healthy() -> None:
    provider = _make_provider()
    _configure_namespace_inspection_provider(
        provider,
        ingress_load_balancer=SimpleNamespace(ingress=[]),
        daemonset_unavailable=0,
    )

    result = provider.run_namespace_inspection("demo", None)

    assert result["health_status"] == "healthy"


def test_log_inspection_continues_when_endpoint_slice_rbac_is_missing() -> None:
    provider = _make_provider()
    _configure_namespace_inspection_provider(
        provider,
        ingress_load_balancer=None,
        daemonset_unavailable=0,
    )
    provider.discovery.list_namespaced_endpoint_slice = (
        lambda namespace, _request_timeout: (_ for _ in ()).throw(
            ApiException(status=403, reason="Forbidden")
        )
    )
    provider.collect_pod_log_samples = (
        lambda namespace, pod_names, limits: TemporaryPodLogCollection()
    )
    original_build = provider._build_pod_result
    provider._build_pod_result = (
        lambda namespace, pod, services, **kwargs: original_build(
            namespace,
            pod,
            services,
        )
    )

    result = provider.run_namespace_inspection(
        "demo",
        None,
        include_logs=True,
    )

    assert result["pods"][0]["status"] == "Running"
    assert result["services"][0]["status"] == "unknown"
    assert result["ingresses"][0]["status"] == "unknown"
    assert result["health_status"] == "warning"


def test_status_pod_result_does_not_read_events_or_logs() -> None:
    provider = _make_provider()
    provider.core.read_namespaced_pod_log = Mock(
        side_effect=AssertionError("status collection must not read logs")
    )
    provider.core.list_namespaced_event = Mock(
        side_effect=AssertionError("status collection must not read events")
    )
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="demo-api-0",
            namespace="demo",
            labels={"app": "api"},
        ),
        spec=SimpleNamespace(
            node_name="node-a",
            containers=[SimpleNamespace(name="api")],
        ),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[],
            conditions=[SimpleNamespace(type="Ready", status="True")],
        ),
    )

    result = provider._build_pod_result("demo", pod, [])

    assert result["events"] == []
    assert result["log_summary"] is None
    assert result["previous_log_summary"] is None
    assert result["container_log_summaries"] == {}
    provider.core.read_namespaced_pod_log.assert_not_called()
    provider.core.list_namespaced_event.assert_not_called()


def test_lightweight_pod_discovery_reads_only_pod_metadata() -> None:
    provider = _make_provider()
    provider.core.list_namespaced_pod = Mock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(
                    metadata=SimpleNamespace(
                        name="demo-api-0",
                        labels={"app": "api"},
                    )
                )
            ]
        )
    )
    provider.core.read_namespaced_pod_log = Mock(
        side_effect=AssertionError("discovery must not read logs")
    )
    provider.core.list_namespaced_event = Mock(
        side_effect=AssertionError("discovery must not read events")
    )

    result = provider.list_namespace_pods("demo", "app=api")

    assert result["pod_count"] == 1
    assert result["pods"] == [
        {"name": "demo-api-0", "labels": {"app": "api"}}
    ]
    provider.core.list_namespaced_pod.assert_called_once_with(
        namespace="demo",
        label_selector="app=api",
        _request_timeout=5,
    )
    provider.core.read_namespaced_pod_log.assert_not_called()
    provider.core.list_namespaced_event.assert_not_called()


def test_targeted_log_collection_reads_only_explicit_pods() -> None:
    provider = _make_provider()
    provider.core.read_namespaced_pod = Mock(
        return_value=SimpleNamespace(
            spec=SimpleNamespace(
                containers=[SimpleNamespace(name="api")]
            ),
            status=SimpleNamespace(container_statuses=[]),
        )
    )
    provider.core.read_namespaced_pod_log = Mock(
        return_value="ERROR target only"
    )

    result = provider.collect_pod_log_samples(
        "demo",
        ["target-api-0"],
        CollectionLimits(),
    )

    assert result.container_samples == {
        "target-api-0": {"api": "ERROR target only"}
    }
    assert result.log_pods_read == 1
    provider.core.read_namespaced_pod.assert_called_once_with(
        name="target-api-0",
        namespace="demo",
        _request_timeout=5,
    )
    assert {
        call.kwargs["name"]
        for call in provider.core.read_namespaced_pod_log.call_args_list
    } == {"target-api-0"}


def test_targeted_log_collection_uses_since_time_and_filters_until_time() -> None:
    provider = _make_provider()
    since_time = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    until_time = datetime(2026, 8, 9, 10, 5, tzinfo=timezone.utc)
    provider.core.read_namespaced_pod = Mock(
        return_value=SimpleNamespace(
            spec=SimpleNamespace(containers=[SimpleNamespace(name="api")]),
            status=SimpleNamespace(container_statuses=[]),
        )
    )
    provider.core.read_namespaced_pod_log = Mock(
        return_value=(
            "2026-08-09T10:01:00Z ERROR inside window\n"
            "2026-08-09T10:06:00Z ERROR outside window"
        )
    )

    result = provider.collect_pod_log_samples(
        "demo",
        ["target-api-0"],
        CollectionLimits(),
        since_time=since_time,
        until_time=until_time,
    )

    assert result.container_samples == {
        "target-api-0": {"api": "2026-08-09T10:01:00Z ERROR inside window"}
    }
    assert result.time_range_start == since_time
    assert result.time_range_end == until_time
    provider.core.read_namespaced_pod_log.assert_called_once()
    assert provider.core.read_namespaced_pod_log.call_args.kwargs["since_time"] == "2026-08-09T10:00:00Z"
    assert provider.core.read_namespaced_pod_log.call_args.kwargs["timestamps"] is True


def test_targeted_log_collection_uses_since_seconds_for_recent_range() -> None:
    provider = _make_provider()
    since_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    provider.core.read_namespaced_pod = Mock(
        return_value=SimpleNamespace(
            spec=SimpleNamespace(containers=[SimpleNamespace(name="api")]),
            status=SimpleNamespace(container_statuses=[]),
        )
    )
    provider.core.read_namespaced_pod_log = Mock(
        return_value=(
            "2026-08-09T09:00:00Z ERROR old window\n"
            f"{datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')} ERROR recent window"
        )
    )

    result = provider.collect_pod_log_samples(
        "demo",
        ["target-api-0"],
        CollectionLimits(),
        since_time=since_time,
    )

    assert result.container_samples == {
        "target-api-0": {"api": f"{provider.core.read_namespaced_pod_log.return_value.splitlines()[1]}"}
    }
    log_kwargs = provider.core.read_namespaced_pod_log.call_args.kwargs
    assert "since_time" not in log_kwargs
    assert 1 <= log_kwargs["since_seconds"] <= 16 * 60
    assert log_kwargs["timestamps"] is True


def test_log_pod_limit_rejects_before_any_log_or_pod_read() -> None:
    provider = _make_provider()
    provider.core.read_namespaced_pod = Mock()
    provider.core.read_namespaced_pod_log = Mock()

    with pytest.raises(LogPodLimitExceededError, match="请缩小范围"):
        provider.collect_pod_log_samples(
            "demo",
            ["api-0", "api-1"],
            CollectionLimits(max_log_pods=1),
        )

    provider.core.read_namespaced_pod.assert_not_called()
    provider.core.read_namespaced_pod_log.assert_not_called()


def test_mock_provider_list_namespaces_returns_multiple_statuses() -> None:
    provider = MockInspectionProvider()

    result = provider.list_namespaces()
    namespaces = result["namespaces"]

    assert len(namespaces) >= 3
    assert {namespace["name"] for namespace in namespaces} >= {
        "demo",
        "prod-core",
        "kube-system",
    }
    assert any(namespace["status"] == "warning" for namespace in namespaces)
    assert any(namespace["status"] == "healthy" for namespace in namespaces)


def test_mock_provider_lists_stable_namespace_label_candidates() -> None:
    provider = MockInspectionProvider()

    result = provider.list_namespace_labels("prod-core")

    assert result["namespace"] == "prod-core"
    assert result["labels"] == [
        {
            "key": "team",
            "values": ["platform"],
            "selector": "team=platform",
            "pod_count": 4,
        },
        {
            "key": "environment",
            "values": ["production"],
            "selector": "environment=production",
            "pod_count": 4,
        },
    ]


def test_mock_provider_filters_temporary_logs_by_recent_range() -> None:
    provider = MockInspectionProvider()

    result = provider.collect_pod_log_samples(
        "demo",
        ["demo-api-0"],
        CollectionLimits(),
        since_time=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    sample = result.container_samples["demo-api-0"]["demo-api"]
    assert "database connection refused" in sample
    assert "old window" not in sample


def test_kubernetes_provider_lists_namespace_label_candidates() -> None:
    provider = _make_provider()
    provider.core.list_namespaced_pod = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(metadata=SimpleNamespace(labels={"app": "api", "team": "platform"})),
            SimpleNamespace(metadata=SimpleNamespace(labels={"app": "api"})),
            SimpleNamespace(metadata=SimpleNamespace(labels=None)),
        ]
    )

    result = provider.list_namespace_labels("demo")

    assert result["namespace"] == "demo"
    assert result["labels"] == [
        {"key": "app", "values": ["api"], "selector": "app=api", "pod_count": 2},
        {"key": "team", "values": ["platform"], "selector": "team=platform", "pod_count": 1},
    ]


def test_kubernetes_provider_collects_log_recording_snapshot_with_since_time() -> None:
    provider = _make_provider()
    since_time = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="demo-api-0",
            namespace="demo",
            uid="uid-0",
            owner_references=[SimpleNamespace(kind="ReplicaSet", name="demo-api-abc")],
        ),
        spec=SimpleNamespace(
            node_name="node-a",
            containers=[SimpleNamespace(name="api"), SimpleNamespace(name="sidecar")],
        ),
    )
    provider.core.list_namespaced_pod = Mock(return_value=SimpleNamespace(items=[pod]))

    def read_log(**kwargs):
        if kwargs["container"] == "api":
            return "2026-08-09T10:00:01Z api started\n2026-08-09T10:00:02Z error happened"
        return ""

    provider.core.read_namespaced_pod_log = Mock(side_effect=read_log)

    snapshot = provider.collect_log_recording_snapshot(
        "demo",
        since_time=since_time,
        max_pods=10,
        max_total_bytes=1024,
        max_pod_bytes=1024,
    )

    provider.core.list_namespaced_pod.assert_called_once_with(namespace="demo", _request_timeout=5)
    assert provider.core.read_namespaced_pod_log.call_args_list[0].kwargs == {
        "name": "demo-api-0",
        "namespace": "demo",
        "container": "api",
        "since_time": "2026-08-09T10:00:00Z",
        "timestamps": True,
        "_request_timeout": 5,
    }
    assert snapshot.namespace == "demo"
    assert snapshot.pods[0].pod_uid == "uid-0"
    assert snapshot.pods[0].owner_kind == "ReplicaSet"
    assert snapshot.pods[0].container_names == ["api", "sidecar"]
    assert [entry.text for entry in snapshot.pods[0].entries] == ["api started", "error happened"]
    assert snapshot.pods[0].entries[0].log_time == datetime(2026, 8, 9, 10, 0, 1, tzinfo=timezone.utc)


def test_kubernetes_provider_log_recording_snapshot_records_log_parameter_errors() -> None:
    provider = _make_provider()
    since_time = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="demo-api-0", namespace="demo", uid="uid-0", owner_references=[]),
        spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="api")]),
    )
    provider.core.list_namespaced_pod = Mock(return_value=SimpleNamespace(items=[pod]))
    provider.core.read_namespaced_pod_log = Mock(side_effect=TypeError("invalid since_time"))

    snapshot = provider.collect_log_recording_snapshot(
        "demo",
        since_time=since_time,
        max_pods=10,
        max_total_bytes=1024,
        max_pod_bytes=1024,
    )

    assert snapshot.pods[0].entries == []
    assert snapshot.pods[0].failures == ["api: TypeError: invalid since_time"]


def test_kubernetes_provider_collect_log_recording_snapshot_enforces_pod_limit() -> None:
    provider = _make_provider()
    provider.core.list_namespaced_pod = Mock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(metadata=SimpleNamespace(name="api-0")),
                SimpleNamespace(metadata=SimpleNamespace(name="api-1")),
            ]
        )
    )

    with pytest.raises(LogPodLimitExceededError):
        provider.collect_log_recording_snapshot(
            "demo",
            since_time=datetime.now(timezone.utc),
            max_pods=1,
            max_total_bytes=1024,
            max_pod_bytes=1024,
        )

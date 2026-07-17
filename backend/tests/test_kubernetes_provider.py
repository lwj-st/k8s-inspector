from types import SimpleNamespace

from app.providers.kubernetes_provider import KubernetesInspectionProvider
from app.providers.mock_provider import MockInspectionProvider


def _make_provider() -> KubernetesInspectionProvider:
    provider = KubernetesInspectionProvider.__new__(KubernetesInspectionProvider)
    provider.settings = SimpleNamespace(k8s_request_timeout=5)
    provider.core = SimpleNamespace()
    provider.apps = SimpleNamespace()
    provider.networking = SimpleNamespace()
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


def _configure_namespace_inspection_provider(
    provider: KubernetesInspectionProvider,
    *,
    ingress_load_balancer: object | None,
    daemonset_unavailable: int,
) -> None:
    provider.core.list_namespaced_pod = lambda namespace, label_selector, _request_timeout: SimpleNamespace(items=[object()])
    provider.core.list_namespaced_service = lambda namespace, label_selector, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="demo-api"),
                spec=SimpleNamespace(type="ClusterIP"),
            )
        ]
    )
    provider.networking.list_namespaced_ingress = lambda namespace, _request_timeout: SimpleNamespace(
        items=[
            SimpleNamespace(
                metadata=SimpleNamespace(name="demo"),
                status=SimpleNamespace(load_balancer=ingress_load_balancer),
                spec=SimpleNamespace(rules=[]),
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
    provider._build_pod_result = lambda namespace, pod, services: {
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


def test_run_namespace_inspection_warns_when_ingress_is_unknown() -> None:
    provider = _make_provider()
    _configure_namespace_inspection_provider(
        provider,
        ingress_load_balancer=None,
        daemonset_unavailable=0,
    )

    result = provider.run_namespace_inspection("demo", None)

    assert result["pods"][0]["status"] == "Running"
    assert result["ingresses"][0]["status"] == "unknown"
    assert result["health_status"] == "warning"


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

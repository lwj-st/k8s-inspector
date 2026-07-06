from types import SimpleNamespace

from app.providers.kubernetes_provider import KubernetesInspectionProvider


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

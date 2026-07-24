from types import SimpleNamespace

from app.providers.kubernetes_provider import KubernetesInspectionProvider
from app.providers.mock_provider import MockInspectionProvider


def _make_provider() -> KubernetesInspectionProvider:
    provider = KubernetesInspectionProvider.__new__(KubernetesInspectionProvider)
    provider.settings = SimpleNamespace(k8s_request_timeout=5, k8s_log_tail_lines=1000, k8s_log_summary_lines=5)
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
        "demo-api": "demo-api-line1\ndemo-api-line2\ndemo-api-line3\ndemo-api-line4\ndemo-api-line5\ndemo-api-line6",
        "sidecar": "sidecar-line1\nsidecar-line2\nsidecar-line3\nsidecar-line4\nsidecar-line5\nsidecar-line6",
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

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from kubernetes.client.exceptions import ApiException

from app.providers.kubernetes_tls import dns_name_matches
from app.providers.kubernetes_collection import (
    KubernetesResourceCollector,
    _latest_cron_schedule,
)
from app.schemas.v1_1 import (
    CollectionLayer,
    InspectionScope,
    InspectionThresholds,
    InspectionTrigger,
    ProviderCollectionRequest,
    ProviderCollectionResult,
    ResourceRef,
)


def ns(**values):
    return SimpleNamespace(**values)


def collector() -> KubernetesResourceCollector:
    return KubernetesResourceCollector(
        settings=ns(k8s_request_timeout=5),
        core=ns(),
        apps=ns(),
        batch=ns(),
        networking=ns(),
        discovery=ns(),
        storage=ns(),
        custom=ns(),
        version_api=ns(),
    )


def namespace_request(*, label_selector: str | None = None) -> ProviderCollectionRequest:
    return ProviderCollectionRequest(
        scope=InspectionScope(type="namespace", namespace="demo", label_selector=label_selector),
        layer=CollectionLayer.status,
        trigger=InspectionTrigger.manual,
    )


def test_status_collection_never_reads_events_logs_or_secrets() -> None:
    item = collector()
    item._collect_namespace_status = (
        lambda namespace, selector, result, **kwargs: None
    )
    item.core.list_namespaced_event = lambda **kwargs: (_ for _ in ()).throw(AssertionError("events must not be read"))
    item.core.read_namespaced_pod_log = lambda **kwargs: (_ for _ in ()).throw(AssertionError("logs must not be read"))
    item.core.list_namespaced_secret = lambda **kwargs: (_ for _ in ()).throw(AssertionError("secrets must not be listed"))

    result = item.collect(namespace_request())

    assert result.log_pods_read == 0
    assert result.collected_log_bytes == 0


def test_namespace_label_selector_is_only_passed_to_pod_list() -> None:
    item = collector()
    calls: list[tuple[str, str | None]] = []
    empty = ns(items=[])
    item.core.list_namespaced_pod = lambda namespace, label_selector, _request_timeout: (
        calls.append(("pods", label_selector)) or empty
    )
    item.core.list_namespaced_service = lambda namespace, _request_timeout: (
        calls.append(("services", None)) or empty
    )
    item.core.list_namespaced_persistent_volume_claim = lambda namespace, _request_timeout: empty
    item.apps.list_namespaced_deployment = lambda namespace, _request_timeout: empty
    item.apps.list_namespaced_stateful_set = lambda namespace, _request_timeout: empty
    item.apps.list_namespaced_daemon_set = lambda namespace, _request_timeout: empty
    item.apps.list_namespaced_replica_set = lambda namespace, _request_timeout: empty
    item.batch.list_namespaced_job = lambda namespace, _request_timeout: empty
    item.batch.list_namespaced_cron_job = lambda namespace, _request_timeout: empty
    item.networking.list_namespaced_ingress = lambda namespace, _request_timeout: empty
    item.discovery.list_namespaced_endpoint_slice = lambda namespace, _request_timeout: empty

    item.collect(namespace_request(label_selector="app=api"))

    assert calls == [("pods", "app=api"), ("services", None)]


def test_endpoint_slice_merges_all_slices_and_ready_null_counts_as_ready() -> None:
    item = collector()
    service = ns(
        metadata=ns(name="api", namespace="demo", uid="svc-1"),
        spec=ns(type="ClusterIP", selector={"app": "api"}, ports=[]),
    )
    pod = ns(
        metadata=ns(name="api-0", namespace="demo", uid="pod-1", labels={"app": "api"}, owner_references=[]),
        spec=ns(node_name="node-a", containers=[], init_containers=[], volumes=[], service_account_name="default", image_pull_secrets=[]),
        status=ns(phase="Running", conditions=[], container_statuses=[], init_container_statuses=[]),
    )
    slices = [
        ns(
            metadata=ns(name="api-a", namespace="demo", labels={"kubernetes.io/service-name": "api"}),
            endpoints=[
                ns(conditions=ns(ready=None), target_ref=ns(kind="Pod", namespace="demo", name="api-0", uid="pod-1"))
            ],
            ports=[],
        ),
        ns(
            metadata=ns(name="api-b", namespace="demo", labels={"kubernetes.io/service-name": "api"}),
            endpoints=[ns(conditions=ns(ready=False), target_ref=None)],
            ports=[],
        ),
    ]

    observations = item._service_observations([service], [pod], slices, ingress_service_names=set())
    service_observation = observations[0]

    assert service_observation.facts["endpoint_slices"] == 2
    assert service_observation.facts["ready_endpoints"] == 1


@pytest.mark.parametrize(
    ("git_version", "supported"),
    [("v1.34.7", True), ("v1.36.0", True), ("v1.33.9", False)],
)
def test_server_version_support_range_is_explicit(git_version: str, supported: bool) -> None:
    item = collector()
    item.version_api.get_code = lambda _request_timeout: ns(git_version=git_version, major="1", minor=git_version.split(".")[1])

    observation = item.collect_server_version()

    assert observation.facts["supported"] is supported
    assert observation.facts["supported_range"] == "1.34-1.36"


def test_evidence_collection_requires_explicit_targets_and_honors_log_budget() -> None:
    item = collector()
    calls: list[str] = []
    item.core.read_namespaced_pod = lambda name, namespace, _request_timeout: ns(
        metadata=ns(name=name, namespace=namespace, uid="pod-1"),
        spec=ns(containers=[ns(name="app")]),
    )
    item.core.read_namespaced_pod_log = lambda **kwargs: calls.append(kwargs["name"]) or "line-1\nline-2"

    request = ProviderCollectionRequest(
        scope=InspectionScope(type="namespace", namespace="demo"),
        layer=CollectionLayer.evidence,
        evidence_targets=[ResourceRef(kind="Pod", namespace="demo", name="api-0")],
        include_logs=True,
        trigger=InspectionTrigger.manual,
    )
    result = item.collect(request)

    assert calls == ["api-0"]
    assert result.log_pods_read == 1
    assert result.collected_log_bytes == len("line-1\nline-2".encode())
    assert all("line-1" not in evidence.summary for evidence in result.evidence)


def test_non_tls_secret_reference_is_targeted_and_payload_is_discarded() -> None:
    item = collector()
    secret = ns(data={"password": "must-not-survive"}, binary_data=None)
    calls = {"secret": 0, "config_map": 0}

    def read_secret(**kwargs):
        calls["secret"] += 1
        return secret

    item.core.read_namespaced_secret = read_secret
    item.core.read_namespaced_service_account = lambda **kwargs: ns()
    item.core.read_namespaced_persistent_volume_claim = lambda **kwargs: ns()

    def missing_config_map(**kwargs):
        calls["config_map"] += 1
        raise ApiException(status=404, reason="Not Found")

    item.core.read_namespaced_config_map = missing_config_map
    pod = ns(
        metadata=ns(name="api-0", namespace="demo", uid="pod-1"),
        spec=ns(
            service_account_name="default",
            image_pull_secrets=[ns(name="registry")],
            containers=[
                ns(
                    env_from=[
                        ns(
                            config_map_ref=ns(
                                name="missing-config",
                                optional=False,
                            ),
                            secret_ref=None,
                        )
                    ],
                    env=[],
                )
            ],
            init_containers=[],
            volumes=[],
        ),
    )
    result = ProviderCollectionResult(layer=CollectionLayer.status)

    missing = item._missing_pod_references(pod, result)
    missing_again = item._missing_pod_references(pod, result)

    assert missing == ["ConfigMap/missing-config"]
    assert missing_again == missing
    assert calls == {"secret": 1, "config_map": 1}
    assert secret.data is None
    assert result.failures == []


def test_tls_secret_is_parsed_in_memory_without_exposing_key_material() -> None:
    item = collector()
    now = datetime.now(timezone.utc)
    item._now = now
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "api.example.com")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "api.example.com")]))
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=20))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("api.example.com")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    secret = ns(
        type="kubernetes.io/tls",
        data={
            "tls.crt": base64.b64encode(
                certificate.public_bytes(serialization.Encoding.PEM)
            ).decode(),
            "tls.key": base64.b64encode(
                private_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            ).decode(),
        },
    )

    facts = item._parse_tls_secret(secret, {"api.example.com"})

    assert facts["parse_ok"] is True
    assert facts["host_match"] is True
    assert facts["key_match"] is True
    assert 19 <= facts["days_until_expiry"] <= 20
    serialized = str(facts)
    assert "PRIVATE KEY" not in serialized
    assert "tls.key" not in serialized


def test_tls_wildcard_matches_one_subdomain_level() -> None:
    assert dns_name_matches("dev-grafana.sensecore.com", "*.sensecore.com") is True
    assert dns_name_matches("deep.dev-grafana.sensecore.com", "*.sensecore.com") is False


def test_tls_secret_reports_only_the_hosts_not_covered_by_san() -> None:
    item = collector()
    now = datetime.now(timezone.utc)
    item._now = now
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "*.sensecore.com")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "*.sensecore.com")]))
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=20))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("*.sensecore.com")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    secret = ns(
        type="kubernetes.io/tls",
        data={
            "tls.crt": base64.b64encode(
                certificate.public_bytes(serialization.Encoding.PEM)
            ).decode(),
            "tls.key": base64.b64encode(
                private_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            ).decode(),
        },
    )

    facts = item._parse_tls_secret(
        secret,
        {"dev-grafana.sensecore.com", "grafana.internal.example.com"},
    )

    assert facts["host_match"] is False
    assert facts["matched_hosts"] == ["dev-grafana.sensecore.com"]
    assert facts["mismatched_hosts"] == ["grafana.internal.example.com"]


def test_old_warning_event_only_survives_window_for_current_fault() -> None:
    item = collector()
    item._now = datetime.now(timezone.utc)
    target = ResourceRef(kind="Pod", namespace="demo", name="api-0")
    old = item._now - timedelta(hours=2)
    item.core.list_namespaced_event = lambda **kwargs: ns(
        items=[
            ns(
                type="Warning",
                reason="FailedMount",
                message="MountVolume failed",
                event_time=None,
                last_timestamp=old,
                count=3,
                metadata=ns(creation_timestamp=old),
            ),
            ns(
                type="Normal",
                reason="Pulled",
                message="Successfully pulled image",
                event_time=None,
                last_timestamp=item._now,
                count=1,
                metadata=ns(creation_timestamp=item._now),
            ),
        ]
    )
    item.core.read_namespaced_pod = lambda **kwargs: ns(
        status=ns(
            phase="Running",
            conditions=[ns(type="Ready", status="True")],
        )
    )
    result = ProviderCollectionResult(layer=CollectionLayer.evidence)

    item._collect_pod_events(target, result)

    assert result.evidence == []
    assert result.observations[0].facts["warning_reasons"] == []


def test_event_evidence_never_persists_raw_message() -> None:
    item = collector()
    item._now = datetime.now(timezone.utc)
    target = ResourceRef(kind="Pod", namespace="demo", name="api-0")
    item.core.list_namespaced_event = lambda **kwargs: ns(
        items=[
            ns(
                type="Warning",
                reason="Unhealthy",
                message="probe failed token=top-secret business-id=42",
                event_time=item._now,
                last_timestamp=None,
                count=1,
                metadata=ns(creation_timestamp=item._now),
            )
        ]
    )
    result = ProviderCollectionResult(layer=CollectionLayer.evidence)

    item._collect_pod_events(target, result)

    serialized = str(
        [evidence.model_dump(mode="json") for evidence in result.evidence]
    )
    assert "top-secret" not in serialized
    assert "business-id" not in serialized
    assert result.evidence[0].summary == "Warning Event: Unhealthy"


@pytest.mark.parametrize(
    ("kind", "namespace", "expected_api"),
    [
        ("PersistentVolumeClaim", "demo", "namespaced"),
        ("PersistentVolume", None, "all_namespaces"),
    ],
)
def test_storage_event_evidence_is_targeted_recent_and_sanitized(
    kind: str,
    namespace: str | None,
    expected_api: str,
) -> None:
    item = collector()
    now = datetime.now(timezone.utc)
    calls: list[tuple[str, str]] = []
    events = ns(
        items=[
            ns(
                type="Normal",
                reason="ProvisioningSucceeded",
                message="normal detail",
                event_time=now,
                last_timestamp=None,
                count=1,
                metadata=ns(creation_timestamp=now),
            ),
            ns(
                type="Warning",
                reason="ProvisioningFailed",
                message="storage-password=top-secret",
                event_time=now,
                last_timestamp=None,
                count=2,
                metadata=ns(creation_timestamp=now),
            ),
            ns(
                type="Warning",
                reason="OldFailure",
                message="expired detail",
                event_time=now - timedelta(minutes=31),
                last_timestamp=None,
                count=3,
                metadata=ns(creation_timestamp=now - timedelta(minutes=31)),
            ),
        ]
    )
    item.core.list_namespaced_event = (
        lambda *, namespace, field_selector, _request_timeout: (
            calls.append(("namespaced", field_selector)) or events
        )
    )
    item.core.list_event_for_all_namespaces = (
        lambda *, field_selector, _request_timeout: (
            calls.append(("all_namespaces", field_selector)) or events
        )
    )
    target = ResourceRef(kind=kind, namespace=namespace, name="storage-a")

    result = item.collect(
        ProviderCollectionRequest(
            scope=(
                InspectionScope(type="namespace", namespace=namespace)
                if namespace
                else InspectionScope(type="cluster")
            ),
            layer=CollectionLayer.evidence,
            evidence_targets=[target],
            include_events=True,
            trigger=InspectionTrigger.manual,
        )
    )

    assert calls == [
        (
            expected_api,
            f"involvedObject.kind={kind},involvedObject.name=storage-a",
        )
    ]
    assert len(result.evidence) == 1
    assert result.evidence[0].summary == "Warning Event: ProvisioningFailed"
    serialized = str(result.model_dump(mode="json"))
    assert "top-secret" not in serialized
    assert "OldFailure" not in serialized


def test_concurrent_collections_keep_thresholds_counters_and_caches_isolated() -> None:
    item = collector()
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    item.core.list_namespaced_event = lambda **kwargs: ns(
        items=[
            ns(
                type="Warning",
                reason="CustomWarning",
                message="safe transient detail",
                event_time=observed_at,
                last_timestamp=None,
                count=1,
                metadata=ns(creation_timestamp=observed_at),
            )
        ]
    )
    target = ResourceRef(kind="Pod", namespace="demo", name="api-0")

    def collect(window: int):
        return item.collect(
            ProviderCollectionRequest(
                scope=InspectionScope(type="pod", namespace="demo", pod_name="api-0"),
                layer=CollectionLayer.evidence,
                thresholds=InspectionThresholds(
                    warning_event_window_minutes=window,
                ),
                evidence_targets=[target],
                include_events=True,
                trigger=InspectionTrigger.manual,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        short, long = list(executor.map(collect, [10, 30]))

    assert short.evidence == []
    assert len(long.evidence) == 1
    assert short.kubernetes_api_calls == 1
    assert long.kubernetes_api_calls == 1


def test_clusterrole_keeps_secret_and_configmap_as_targeted_get_only() -> None:
    clusterrole = (
        Path(__file__).parents[2]
        / "deploy/helm/k8s-inspector/templates/clusterrole.yaml"
    ).read_text()

    assert 'resources: ["secrets", "configmaps"]\n    verbs: ["get"]' in clusterrole
    assert 'resources: ["pods/log"]\n    verbs: ["get"]' in clusterrole
    assert (
        'apiGroups: ["discovery.k8s.io"]\n'
        '    resources: ["endpointslices"]\n'
        '    verbs: ["get", "list"]'
    ) in clusterrole
    for forbidden in ("create", "update", "patch", "delete"):
        assert f'"{forbidden}"' not in clusterrole


def test_cluster_collection_reuses_cluster_scoped_lookup_results() -> None:
    item = collector()
    item.version_api.get_code = lambda _request_timeout: ns(
        git_version="v1.36.0",
        major="1",
        minor="36",
    )
    item.core.list_namespace = lambda _request_timeout: ns(
        items=[
            ns(metadata=ns(name="demo")),
            ns(metadata=ns(name="prod")),
        ]
    )
    calls = {"ingress_classes": 0, "storage_classes": 0}

    def ingress_classes(result):
        calls["ingress_classes"] += 1
        return {"nginx"}

    def storage_classes(result):
        calls["storage_classes"] += 1
        return {"standard": "WaitForFirstConsumer"}

    namespace_calls: list[tuple[str, bool, set[str], dict]] = []
    item._list_ingress_classes = ingress_classes
    item._list_storage_class_modes = storage_classes
    item._collect_namespace_status = (
        lambda namespace, selector, result, **kwargs: namespace_calls.append(
            (
                namespace,
                kwargs["include_metrics"],
                kwargs["ingress_classes"],
                kwargs["storage_class_modes"],
            )
        )
    )
    item._collect_cluster_status = lambda result, **kwargs: None

    item.collect(
        ProviderCollectionRequest(
            scope=InspectionScope(type="cluster"),
            layer=CollectionLayer.status,
            trigger=InspectionTrigger.scheduled,
        )
    )

    assert calls == {"ingress_classes": 1, "storage_classes": 1}
    assert namespace_calls == [
        (
            "demo",
            False,
            {"nginx"},
            {"standard": "WaitForFirstConsumer"},
        ),
        (
            "prod",
            False,
            {"nginx"},
            {"standard": "WaitForFirstConsumer"},
        ),
    ]


def test_deployment_pod_relationship_follows_owner_references() -> None:
    item = collector()
    replica_set = ns(
        metadata=ns(
            name="api-7c8f6f",
            owner_references=[
                ns(
                    kind="Deployment",
                    name="api",
                    controller=True,
                )
            ],
        )
    )
    pod = ns(
        metadata=ns(
            name="unrelated-pod-name",
            owner_references=[
                ns(
                    kind="ReplicaSet",
                    name="api-7c8f6f",
                    controller=True,
                )
            ],
        )
    )

    relationships = item._pod_workload_owner_map([pod], [replica_set])

    assert relationships == {
        "unrelated-pod-name": ("Deployment", "api")
    }


def test_cron_schedule_calculation_respects_timezone_and_observation_grace() -> None:
    now = datetime(2026, 7, 26, 8, 10, tzinfo=timezone.utc)

    latest = _latest_cron_schedule(
        "0 16 * * *",
        "Asia/Shanghai",
        now,
    )

    assert latest == datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    assert _latest_cron_schedule("@hourly", "UTC", now) == datetime(
        2026,
        7,
        26,
        8,
        0,
        tzinfo=timezone.utc,
    )
    assert _latest_cron_schedule(
        "0 8 * JUL MON",
        "UTC",
        now,
    ) == datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def test_invalid_cron_schedule_becomes_collection_failure() -> None:
    item = collector()
    item._now = datetime(2026, 7, 26, 8, 10, tzinfo=timezone.utc)
    cronjob = ns(
        metadata=ns(
            name="bad-cron",
            namespace="demo",
            uid="cron-1",
            labels={},
            creation_timestamp=item._now - timedelta(days=1),
        ),
        spec=ns(
            schedule="not-a-cron",
            time_zone="UTC",
            suspend=False,
            starting_deadline_seconds=None,
        ),
        status=ns(last_schedule_time=None),
    )
    result = ProviderCollectionResult(layer=CollectionLayer.status)

    item._workload_observations(
        "demo",
        deployments=[],
        statefulsets=[],
        daemonsets=[],
        jobs=[],
        cronjobs=[cronjob],
        pods=[],
        replicasets=[],
        result=result,
    )

    assert result.failures[0].check_code == "workload.status"
    assert result.failures[0].error_code == "CRON_SCHEDULE_INVALID"


def test_label_selected_pods_only_pull_resources_with_real_relationships() -> None:
    item = collector()
    pod = ns(
        metadata=ns(
            name="api-0",
            labels={"app": "api", "team": "platform"},
            owner_references=[],
        ),
        spec=ns(volumes=[]),
    )
    related_service = ns(
        metadata=ns(name="api"),
        spec=ns(selector={"app": "api"}),
    )
    unrelated_service = ns(
        metadata=ns(name="worker"),
        spec=ns(selector={"app": "worker"}),
    )

    def ingress(name, service_name):
        return ns(
            metadata=ns(name=name),
            spec=ns(
                default_backend=ns(
                    service=ns(name=service_name),
                ),
                rules=[],
            ),
        )

    filtered = item._filter_collections_for_target_pods(
        {
            "pods": [pod],
            "services": [related_service, unrelated_service],
            "deployments": [],
            "statefulsets": [],
            "daemonsets": [],
            "replicasets": [],
            "jobs": [],
            "cronjobs": [],
            "ingresses": [
                ingress("api", "api"),
                ingress("worker", "worker"),
            ],
            "slices": [],
            "pvcs": [],
        }
    )

    assert [service.metadata.name for service in filtered["services"]] == [
        "api"
    ]
    assert [ingress.metadata.name for ingress in filtered["ingresses"]] == [
        "api"
    ]


def test_restart_delta_uses_windowed_samples_not_lifetime_total() -> None:
    item = collector()
    pod = ns(
        metadata=ns(
            uid="pod-uid",
            namespace="demo",
            name="api-0",
        )
    )
    item._now = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)

    assert item._restart_delta(pod, 100) == 0

    item._now += timedelta(minutes=5)
    assert item._restart_delta(pod, 103) == 3

    item._now += timedelta(minutes=11)
    assert item._restart_delta(pod, 200) == 0

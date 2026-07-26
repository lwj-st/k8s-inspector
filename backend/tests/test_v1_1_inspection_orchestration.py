from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Issue as IssueModel
from app.models import IssueScopeMembership
from app.models import InspectionRecord
from app.models import InspectionCheckResult as InspectionCheckResultModel
from app.models import InspectionRun as InspectionRunModel
from app.models import IssueEvent as IssueEventModel
from app.providers.mock_provider import MockInspectionProvider
from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    CollectionLayer,
    Coverage,
    Evidence,
    EvidenceSource,
    InspectionScope,
    InspectionTrigger,
    ProviderCollectionFailure,
    ProviderCollectionResult,
    ProviderObservation,
    ResourceRef,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    NotificationEventType,
    build_inspection_scope_key,
)
from app.services import inspection_run_service
from app.services import notification_service
from app.services.notification_adapter import build_generic_payload
from app.services.inspection_run_service import execute_inspection, get_run
from app.services.inspection_service import sanitize_persistence_payload
from app.services.retention_service import cleanup_expired_data


class PartiallyFailingProvider:
    def __init__(self):
        self.delegate = MockInspectionProvider()

    def collect_resources(self, request):
        if request.scope.namespace == "broken":
            raise TimeoutError("namespace timeout")
        return self.delegate.collect_resources(request)


class AlwaysFailingProvider:
    def collect_resources(self, request):
        raise TimeoutError("all namespaces failed")


class HighMetricProvider:
    def collect_resources(self, request):
        now = datetime.now(timezone.utc)
        namespace = request.scope.namespace or "demo"
        return ProviderCollectionResult(
            layer=CollectionLayer.status,
            observations=[
                ProviderObservation(
                    resource=ResourceRef(kind="KubernetesVersion", name="server"),
                    observed_at=now,
                    observed_state="v1.36.0",
                    facts={"supported": True},
                ),
                ProviderObservation(
                    resource=ResourceRef(kind="PodMetric", namespace=namespace, name="api-0"),
                    observed_at=now,
                    observed_state="current",
                    facts={
                        "metrics_available": True,
                        "stale": False,
                        "cpu_usage_millicores": 950,
                        "memory_usage_bytes": 950,
                        "cpu_limit_millicores": 1000,
                        "memory_limit_bytes": 1000,
                        "cpu_limit_percent": 95,
                        "memory_limit_percent": 95,
                        "consecutive_cpu_over_threshold": 0,
                        "consecutive_memory_over_threshold": 0,
                    },
                ),
            ],
        )


class KubernetesVersionProvider:
    def __init__(self, *, version: str, supported: bool):
        self.version = version
        self.supported = supported

    def collect_resources(self, request):
        return ProviderCollectionResult(
            layer=CollectionLayer.status,
            observations=[
                ProviderObservation(
                    resource=ResourceRef(kind="KubernetesVersion", name="server"),
                    observed_at=datetime.now(timezone.utc),
                    observed_state=self.version,
                    facts={"supported": self.supported},
                )
            ],
            kubernetes_api_calls=1,
        )


class KubernetesVersionFailureProvider:
    def collect_resources(self, request):
        return ProviderCollectionResult(
            layer=CollectionLayer.status,
            failures=[
                ProviderCollectionFailure(
                    check_code="kubernetes.version",
                    error_code="VERSION_API_FAILED",
                    message="测试版本接口失败",
                    retryable=True,
                )
            ],
            kubernetes_api_calls=1,
        )


def test_namespace_failure_is_scoped_and_top_coverage_is_aggregated(client):
    scope = InspectionScope(type="namespace", namespaces=["demo", "broken"])
    with client.app.state.session_factory() as session:
        run, _ = execute_inspection(
            session,
            provider=PartiallyFailingProvider(),
            cluster_id="cluster-a",
            scope=scope,
            trigger=InspectionTrigger.scheduled,
        )
        assert run.status.value == "partial"
        assert len({item.check_code for item in run.coverage}) == len(run.coverage)
        failed = next(item for item in run.coverage if item.check_code == "inspection.scope")
        assert failed.status.value == "failed"
        assert "名称空间采集失败" in failed.reason
        detail = get_run(session, run.id)
        scoped = [
            item
            for item in detail.check_results
            if item.check_code == "inspection.scope"
        ]
        assert len(scoped) == 1
        assert scoped[0].scope.namespace == "broken"


def test_all_namespace_failures_create_valid_failed_run(client):
    scope = InspectionScope(type="namespace", namespaces=["a", "b"])
    with client.app.state.session_factory() as session:
        run, _ = execute_inspection(
            session,
            provider=AlwaysFailingProvider(),
            cluster_id="cluster-a",
            scope=scope,
            trigger=InspectionTrigger.scheduled,
        )
        assert run.status.value == "failed"
        assert run.error_code == "INSPECTION_ALL_CHECKS_FAILED"
        assert run.error_message
        assert len(run.coverage) == 1
        assert run.coverage[0].check_code == "inspection.scope"


def test_metric_issue_requires_three_scheduled_cycles(client):
    scope = InspectionScope(type="namespace", namespace="demo")
    with client.app.state.session_factory() as session:
        runs = []
        for _ in range(3):
            run, _ = execute_inspection(
                session,
                provider=HighMetricProvider(),
                cluster_id="cluster-metric",
                scope=scope,
                trigger=InspectionTrigger.scheduled,
            )
            runs.append(run)
        assert runs[0].issue_ids == []
        assert runs[1].issue_ids == []
        issue = session.query(IssueModel).filter_by(cluster_id="cluster-metric").one()
        assert issue.issue_code == "RESOURCE_USAGE_HIGH"
        assert issue.id in runs[2].issue_ids


def test_retention_never_deletes_recovered_issue_with_active_membership(client):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=100)
    with client.app.state.session_factory() as session:
        protected = _recovered_issue("d" * 64, "protected", old)
        removable = _recovered_issue("e" * 64, "removable", old)
        session.add_all([protected, removable])
        session.flush()
        session.add_all(
            [
                IssueScopeMembership(
                    issue_id=protected.id,
                    scope_key="1" * 64,
                    active=True,
                    last_seen_at=old,
                    deactivated_at=None,
                ),
                IssueScopeMembership(
                    issue_id=removable.id,
                    scope_key="2" * 64,
                    active=False,
                    last_seen_at=old,
                    deactivated_at=old,
                ),
            ]
        )
        session.commit()
        protected_id = protected.id
        removable_id = removable.id
        result = cleanup_expired_data(session, now=now)
        assert result["recovered_issues"] == 1
        assert session.get(IssueModel, protected_id) is not None
        assert session.get(IssueModel, removable_id) is None


def test_persistence_sanitizer_is_detached_bounded_and_removes_raw_logs():
    original = {
        "pod": {
            "container_log_summaries": {"api": "raw line\n" * 100},
            "log_summary": "Bearer very-secret-token\n" + "x" * 3000,
            "password": "plain-password",
            "detail": "https://open.feishu.cn/open-apis/bot/v2/hook/secret-token",
        }
    }
    sanitized = sanitize_persistence_payload(original)
    assert "container_log_summaries" in original["pod"]
    assert "container_log_summaries" not in sanitized["pod"]
    assert "very-secret-token" not in str(sanitized)
    assert "plain-password" not in str(sanitized)
    assert "secret-token" not in str(sanitized)
    assert len(sanitized["pod"]["log_summary"]) < 2100
    assert sanitized["_persistence_sanitization"] == {
        "raw_logs_removed": True,
        "truncated": True,
    }


def test_all_inspection_entrypoints_persist_only_sanitized_dtos(client):
    responses = [
        client.post("/api/v1/inspections/cluster/run"),
        client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"}),
        client.post(
            "/api/v1/inspections/namespaces/run",
            json={"namespaces": ["demo"], "all_namespaces": False},
        ),
        client.post(
            "/api/v1/inspections/pod/run",
            json={"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
        ),
    ]
    assert all(item.status_code == 200 for item in responses)
    assert responses[-1].json()["pod"]["log_summary"]
    with client.app.state.session_factory() as session:
        records = session.query(InspectionRecord).order_by(InspectionRecord.id).all()
        assert {item.inspection_type for item in records} >= {
            "cluster",
            "namespace",
            "namespaces",
            "pod",
        }
        serialized = str([item.result_payload for item in records])
        assert "container_log_summaries" not in serialized
        assert "PRIVATE KEY" not in serialized
        for record in records:
            _assert_no_unsafe_keys(record.result_payload)


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/inspections/cluster/run", None),
        ("/api/v1/inspections/namespace/run", {"namespace": "demo"}),
        (
            "/api/v1/inspections/namespaces/run",
            {"namespaces": ["demo"], "all_namespaces": False},
        ),
        (
            "/api/v1/inspections/pod/run",
            {"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
        ),
        (
            "/api/v1/inspections/run",
            {"target_type": "namespace", "namespace": "demo"},
        ),
    ],
)
def test_manual_inspection_entrypoints_update_last_inspection(client, path, payload):
    response = client.post(path, json=payload) if payload is not None else client.post(path)
    assert response.status_code == 200

    last_inspection = client.get("/api/v1/system/status").json()["last_inspection"]
    assert last_inspection["state"] != "unavailable"
    assert last_inspection["details"]["run_id"] > 0


def test_mock_inspection_never_claims_a_real_kubernetes_connection(client):
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo"},
    )
    assert response.status_code == 200

    kubernetes_api = client.get("/api/v1/system/status").json()["kubernetes_api"]
    assert kubernetes_api["state"] == "unavailable"
    assert kubernetes_api["details"] == {"mode": "mock"}


@pytest.mark.parametrize(
    ("run_status", "expected_state"),
    [
        ("partial", "degraded"),
        ("failed", "failed"),
        ("succeeded", "ok"),
    ],
)
def test_manual_inspection_status_mapping(
    client,
    monkeypatch,
    run_status,
    expected_state,
):
    if run_status == "failed":

        def fail_collection(_request):
            raise TimeoutError("test collection timeout")

        monkeypatch.setattr(
            client.app.state.provider,
            "collect_resources",
            fail_collection,
        )
    elif run_status == "succeeded":

        def pass_collection(_result, *, scope, policy, trigger, now=None):
            return [
                CheckEvaluation(
                    scope=scope,
                    scope_key=build_inspection_scope_key(scope),
                    coverage=Coverage(
                        check_code="test.passed",
                        name="测试通过",
                        status=CheckStatus.passed,
                        checked_objects=1,
                        duration_ms=1,
                        issue_count=0,
                    ),
                    issue_candidates=[],
                )
            ]

        monkeypatch.setattr(
            inspection_run_service,
            "evaluate_resource_collection",
            pass_collection,
        )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo"},
    )
    assert response.status_code == 200
    with client.app.state.session_factory() as session:
        latest = session.query(InspectionRunModel).order_by(InspectionRunModel.id.desc()).first()
        assert latest.status == run_status

    last_inspection = client.get("/api/v1/system/status").json()["last_inspection"]
    assert last_inspection["state"] == expected_state
    assert last_inspection["message"] == f"最近巡检状态：{run_status}"


def test_last_inspection_is_restored_after_app_restart(test_settings):
    first_app = create_app(test_settings)
    with TestClient(first_app) as first:
        response = first.post(
            "/api/v1/inspections/namespace/run",
            json={"namespace": "demo"},
        )
        assert response.status_code == 200
        before_restart = first.get("/api/v1/system/status").json()["last_inspection"]
        assert before_restart["state"] == "degraded"
        run_id = before_restart["details"]["run_id"]

    restarted_app = create_app(test_settings)
    with TestClient(restarted_app) as restarted:
        after_restart = restarted.get("/api/v1/system/status").json()["last_inspection"]
        assert after_restart["state"] == "degraded"
        assert after_restart["message"] == "最近巡检状态：partial"
        assert after_restart["details"] == {
            "run_id": run_id,
            "status": "partial",
            "restored_from_database": True,
        }


@pytest.mark.parametrize("supported", [True, False])
def test_kubernetes_provider_updates_real_version_registry(client, supported):
    registry = client.app.state.component_status_registry
    version = "v1.36.1" if supported else "v1.37.0"
    with client.app.state.session_factory() as session:
        execute_inspection(
            session,
            provider=KubernetesVersionProvider(
                version=version,
                supported=supported,
            ),
            cluster_id="cluster-kubernetes",
            scope=InspectionScope(type="cluster"),
            trigger=InspectionTrigger.manual,
            registry=registry,
            provider_mode="kubernetes",
        )

    status = registry.get("kubernetes_api")
    assert status.state.value == "ok"
    assert status.details == {
        "mode": "kubernetes",
        "successful_version_observations": 1,
        "failed_scope_count": 0,
    }
    assert registry.kubernetes_version() == (version, supported)


def test_kubernetes_version_api_failures_clear_version_and_report_scope_count(client):
    registry = client.app.state.component_status_registry
    registry.update_kubernetes_version("v1.36.1", True)
    with client.app.state.session_factory() as session:
        execute_inspection(
            session,
            provider=KubernetesVersionFailureProvider(),
            cluster_id="cluster-kubernetes",
            scope=InspectionScope(
                type="namespace",
                namespaces=["team-a", "team-b"],
            ),
            trigger=InspectionTrigger.scheduled,
            registry=registry,
            provider_mode="kubernetes",
        )

    status = registry.get("kubernetes_api")
    assert status.state.value == "failed"
    assert status.details == {
        "mode": "kubernetes",
        "failed_scope_count": 2,
        "scope_count": 2,
        "successful_business_observations": 0,
    }
    assert registry.kubernetes_version() == (None, None)


def test_version_permission_failure_is_degraded_when_business_collection_succeeds(client):
    class PartiallyAuthorizedProvider(KubernetesVersionFailureProvider):
        def collect_resources(self, request):
            result = super().collect_resources(request)
            result.observations.append(
                ProviderObservation(
                    resource=ResourceRef(
                        kind="Pod",
                        namespace=request.scope.namespace,
                        name="api-0",
                    ),
                    observed_at=datetime.now(timezone.utc),
                    observed_state="Running",
                    facts={},
                )
            )
            return result

    registry = client.app.state.component_status_registry
    with client.app.state.session_factory() as session:
        execute_inspection(
            session,
            provider=PartiallyAuthorizedProvider(),
            cluster_id="cluster-kubernetes",
            scope=InspectionScope(type="namespace", namespace="team-a"),
            trigger=InspectionTrigger.manual,
            registry=registry,
            provider_mode="kubernetes",
        )

    status = registry.get("kubernetes_api")
    assert status.state.value == "degraded"
    assert status.details == {
        "mode": "kubernetes",
        "failed_scope_count": 1,
        "scope_count": 1,
        "successful_business_observations": 1,
    }


def test_issue_run_query_ack_and_notification_chain_never_exposes_secrets(
    client,
    monkeypatch,
):
    dirty = (
        "password=p1 passwd=p2 access_token=a1 refresh-token=r1 "
        "session token=s1 token=t1 secret=x1 API key=k1 Bearer bearer1 "
        "https://open.feishu.cn/open-apis/bot/v2/hook/hook1 "
        "-----BEGIN PRIVATE KEY-----private1-----END PRIVATE KEY----- "
        "ERROR upstream unavailable"
    )
    forbidden = {
        "p1", "p2", "a1", "r1", "s1", "t1", "x1", "k1",
        "bearer1", "hook1", "private1",
    }

    def dirty_evaluation(_result, *, scope, policy, trigger, now=None):
        candidate = IssueCandidate(
            issue_code=IssueCode.POD_NOT_READY,
            severity=IssueSeverity.warning,
            scope=IssueScope.pod,
            resource=ResourceRef(kind="Pod", namespace="demo", name="api-0"),
            summary=dirty,
            reason=dirty,
            suggestion=dirty,
            evidence=[
                Evidence(
                    code="dirty.evidence",
                    source=EvidenceSource.kubernetes_api,
                    summary=dirty,
                    facts={"message": dirty, "items": [dirty]},
                    observed_at=now or datetime.now(timezone.utc),
                )
            ],
            source_check="test.dirty",
        )
        return [
            CheckEvaluation(
                scope=scope,
                scope_key=build_inspection_scope_key(scope),
                coverage=Coverage(
                    check_code="test.dirty",
                    name=dirty,
                    status=CheckStatus.abnormal,
                    reason=dirty,
                    checked_objects=1,
                    duration_ms=1,
                    issue_count=1,
                ),
                issue_candidates=[candidate],
            )
        ]

    monkeypatch.setattr(
        inspection_run_service,
        "evaluate_resource_collection",
        dirty_evaluation,
    )
    with client.app.state.session_factory() as session:
        run, _ = execute_inspection(
            session,
            provider=MockInspectionProvider(),
            cluster_id="cluster-sensitive",
            scope=InspectionScope(type="namespace", namespace="demo"),
            trigger=InspectionTrigger.manual,
        )
        issue = session.query(IssueModel).filter_by(cluster_id="cluster-sensitive").one()
        check = session.query(InspectionCheckResultModel).filter_by(run_id=run.id).one()
        persisted = str(
            {
                "issue": [issue.summary, issue.reason, issue.suggestion, issue.evidence],
                "coverage": session.get(InspectionRunModel, run.id).coverage,
                "check": [check.name, check.reason],
            }
        )
        assert all(secret not in persisted for secret in forbidden)
        assert "ERROR upstream unavailable" in persisted
        assert len(issue.evidence) == 1
        issue_id = issue.id

    acknowledged = client.post(
        f"/api/v1/issues/{issue_id}/acknowledge",
        json={"note": dirty},
    )
    assert acknowledged.status_code == 200
    assert all(secret not in str(acknowledged.json()) for secret in forbidden)
    assert "ERROR upstream unavailable" in acknowledged.json()["acknowledge_note"]

    with client.app.state.session_factory() as session:
        issue = session.get(IssueModel, issue_id)
        message = notification_service._issue_message(
            client.app.state.settings,
            issue,
            NotificationEventType.issue_opened,
        )
        notification_payload = build_generic_payload(message)
        assert all(secret not in str(notification_payload) for secret in forbidden)
        assert "ERROR upstream unavailable" in str(notification_payload)

        issue.summary = issue.reason = issue.suggestion = dirty
        issue.evidence = [{"code": "dirty.evidence", "source": "kubernetes_api", "summary": dirty,
                           "facts": {"message": dirty}, "related_resources": [],
                           "observed_at": datetime.now(timezone.utc).isoformat(), "truncated": False}]
        issue.acknowledge_note = dirty
        row = session.get(InspectionRunModel, run.id)
        row.coverage = [{**row.coverage[0], "name": dirty, "reason": dirty}]
        check = session.query(InspectionCheckResultModel).filter_by(run_id=run.id).one()
        check.name = check.reason = dirty
        for event in session.query(IssueEventModel).filter_by(issue_id=issue_id):
            event.summary = dirty
        session.commit()

    responses = [
        client.get(f"/api/v1/issues/{issue_id}"),
        client.get("/api/v1/issues"),
        client.get(f"/api/v1/issues/{issue_id}/events"),
        client.get(f"/api/v1/inspection-runs/{run.id}"),
        client.get("/api/v1/inspection-runs"),
    ]
    for response in responses:
        assert response.status_code == 200
        serialized = str(response.json())
        assert all(secret not in serialized for secret in forbidden)
        assert "ERROR upstream unavailable" in serialized


def _assert_no_unsafe_keys(value):
    if isinstance(value, dict):
        assert not set(value).intersection(
            {"container_log_summaries", "raw_log", "raw_logs", "log_text", "full_log", "pod_logs"}
        )
        for item in value.values():
            _assert_no_unsafe_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_unsafe_keys(item)


def _recovered_issue(fingerprint: str, name: str, when: datetime) -> IssueModel:
    return IssueModel(
        cluster_id="cluster-retention",
        issue_code="POD_NOT_READY",
        fingerprint=fingerprint,
        severity="warning",
        status="recovered",
        scope="pod",
        resource_kind="Pod",
        resource_namespace="demo",
        resource_name=name,
        summary="已恢复问题",
        reason="测试",
        suggestion="测试",
        evidence=[],
        first_seen_at=when,
        last_seen_at=when,
        recovered_at=when,
        occurrence_count=1,
        source_check="pod.runtime",
        created_at=when,
        updated_at=when,
    )

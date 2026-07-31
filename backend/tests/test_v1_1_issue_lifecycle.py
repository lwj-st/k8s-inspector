from datetime import datetime, timedelta, timezone

from app.models import InspectionRun as InspectionRunModel
from app.models import Issue as IssueModel
from app.models import IssueScopeMembership
from app.models.v1_1 import inspection_run_issues
from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    Coverage,
    InspectionScope,
    InspectionTrigger,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ResourceRef,
    build_inspection_scope_key,
)
from app.services.issue_lifecycle import apply_evaluations


def _run(session, scope: InspectionScope, when: datetime) -> InspectionRunModel:
    row = InspectionRunModel(
        trigger="manual",
        status="running",
        scope=scope.model_dump(mode="json"),
        started_at=when,
        coverage=[],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _evaluation(scope: InspectionScope, *, present: bool, status: CheckStatus | None = None):
    candidate = IssueCandidate(
        issue_code=IssueCode.POD_NOT_READY,
        severity=IssueSeverity.warning,
        scope=IssueScope.pod,
        resource=ResourceRef(kind="Pod", namespace="demo", name="api-0"),
        summary="Pod 未就绪",
        reason="Ready=False",
        suggestion="检查容器状态",
        source_check="pod.runtime",
    )
    candidates = [candidate] if present else []
    check_status = status or (CheckStatus.abnormal if present else CheckStatus.passed)
    return CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code="pod.runtime",
            name="Pod 运行状态",
            status=check_status,
            reason=None if check_status == CheckStatus.passed else "发现异常" if present else "检查失败",
            checked_objects=1,
            duration_ms=1,
            issue_count=len(candidates),
        ),
        issue_candidates=candidates,
    )


def _service_evaluation(scope: InspectionScope, *, present: bool):
    candidate = IssueCandidate(
        issue_code=IssueCode.SERVICE_NO_READY_ENDPOINT,
        severity=IssueSeverity.warning,
        scope=IssueScope.service,
        resource=ResourceRef(kind="Service", namespace="demo", name="helloworld"),
        summary="Service helloworld 没有 Ready Endpoint",
        reason="Ready Endpoint 数量为 0。",
        suggestion="检查 Service selector、Pod Ready 和 EndpointSlice。",
        source_check="service.endpoints",
    )
    candidates = [candidate] if present else []
    return CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code="service.endpoints",
            name="Service 与 EndpointSlice",
            status=CheckStatus.abnormal if present else CheckStatus.passed,
            reason="发现异常" if present else None,
            checked_objects=1 if present else 0,
            duration_ms=1,
            issue_count=len(candidates),
        ),
        issue_candidates=candidates,
    )


def _required_component_evaluation(scope: InspectionScope, *, present: bool):
    candidate = IssueCandidate(
        issue_code=IssueCode.REQUIRED_COMPONENT_MISSING,
        severity=IssueSeverity.critical,
        scope=IssueScope.workload,
        resource=ResourceRef(kind="DaemonSet", namespace="kube-system", name="Calico Node"),
        summary="必需组件 Calico Node 不存在",
        reason="未找到 namespace=kube-system、kind=DaemonSet、selector=k8s-app=calico-node 的对象。",
        suggestion="确认组件是否安装，或修正必需组件定位策略。",
        source_check="required_components",
    )
    candidates = [candidate] if present else []
    return CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code="required_components",
            name="必需组件",
            status=CheckStatus.abnormal if present else CheckStatus.passed,
            reason="发现异常" if present else None,
            checked_objects=10,
            duration_ms=1,
            issue_count=len(candidates),
        ),
        issue_candidates=candidates,
    )


def test_multi_scope_membership_delays_recovery_until_all_scopes_clear(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    namespace_scope = InspectionScope(type="namespace", namespace="demo")
    pod_scope = InspectionScope(type="pod", namespace="demo", pod_name="api-0")
    with session_factory() as session:
        run1 = _run(session, namespace_scope, now)
        first = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run1.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(namespace_scope, present=True)],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(first.issue_ids))

        run2 = _run(session, pod_scope, now + timedelta(minutes=1))
        apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run2.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(pod_scope, present=True)],
            occurred_at=now + timedelta(minutes=1),
        )
        session.commit()
        memberships = session.query(IssueScopeMembership).filter_by(issue_id=issue_id).all()
        assert len(memberships) == 2
        assert all(item.active for item in memberships)

        run3 = _run(session, namespace_scope, now + timedelta(minutes=2))
        partial_clear = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run3.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(namespace_scope, present=False)],
            occurred_at=now + timedelta(minutes=2),
        )
        session.commit()
        assert partial_clear.recovered_count == 0
        assert session.get(IssueModel, issue_id).status == "open"

        run4 = _run(session, pod_scope, now + timedelta(minutes=3))
        recovered = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run4.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(pod_scope, present=False)],
            occurred_at=now + timedelta(minutes=3),
        )
        session.commit()
        assert recovered.recovered_count == 1
        assert recovered.issue_ids == {issue_id}
        assert session.get(IssueModel, issue_id).status == "recovered"
        linked = session.execute(
            inspection_run_issues.select().where(
                inspection_run_issues.c.run_id == run4.id,
                inspection_run_issues.c.issue_id == issue_id,
            )
        ).first()
        assert linked is not None

        run5 = _run(session, pod_scope, now + timedelta(minutes=4))
        reopened = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run5.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(pod_scope, present=True)],
            occurred_at=now + timedelta(minutes=4),
        )
        session.commit()
        assert reopened.opened_count == 1


def test_required_components_global_pass_recovers_old_namespace_scope_false_positive(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    old_namespace_scope = InspectionScope(type="namespace", namespace="platform")
    cluster_scope = InspectionScope(type="cluster")
    with session_factory() as session:
        run1 = _run(session, old_namespace_scope, now)
        opened = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run1.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_required_component_evaluation(old_namespace_scope, present=True)],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(opened.issue_ids))
        membership = session.get(
            IssueScopeMembership,
            {
                "issue_id": issue_id,
                "scope_key": build_inspection_scope_key(old_namespace_scope),
            },
        )
        assert membership is not None and membership.active

        run2 = _run(session, cluster_scope, now + timedelta(minutes=1))
        recovered = apply_evaluations(
            session,
            cluster_id="cluster-a",
            run_id=run2.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_required_component_evaluation(cluster_scope, present=False)],
            occurred_at=now + timedelta(minutes=1),
        )
        session.commit()

        assert recovered.recovered_count == 1
        assert recovered.issue_ids == {issue_id}
        assert session.get(IssueModel, issue_id).status == "recovered"
        session.refresh(membership)
        assert membership.active is False


def test_deleted_service_recovers_previous_service_issue(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    scope = InspectionScope(type="namespace", namespace="demo")
    with session_factory() as session:
        first_run = _run(session, scope, now)
        first = apply_evaluations(
            session,
            cluster_id="cluster-service-delete",
            run_id=first_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_service_evaluation(scope, present=True)],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(first.issue_ids))
        assert session.get(IssueModel, issue_id).status == "open"

        second_run = _run(session, scope, now + timedelta(minutes=1))
        recovered = apply_evaluations(
            session,
            cluster_id="cluster-service-delete",
            run_id=second_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_service_evaluation(scope, present=False)],
            occurred_at=now + timedelta(minutes=1),
        )
        session.commit()

        assert recovered.recovered_count == 1
        assert recovered.issue_ids == {issue_id}
        assert session.get(IssueModel, issue_id).status == "recovered"


def test_failed_check_does_not_deactivate_membership(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    scope = InspectionScope(type="namespace", namespace="demo")
    with session_factory() as session:
        first_run = _run(session, scope, now)
        first = apply_evaluations(
            session,
            cluster_id="cluster-b",
            run_id=first_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(scope, present=True)],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(first.issue_ids))
        failed_run = _run(session, scope, now + timedelta(minutes=1))
        result = apply_evaluations(
            session,
            cluster_id="cluster-b",
            run_id=failed_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(scope, present=False, status=CheckStatus.failed)],
            occurred_at=now + timedelta(minutes=1),
        )
        session.commit()
        assert result.recovered_count == 0
        assert session.get(IssueModel, issue_id).status == "open"
        membership = session.get(
            IssueScopeMembership,
            {"issue_id": issue_id, "scope_key": build_inspection_scope_key(scope)},
        )
        assert membership.active is True


def test_issue_acknowledgement_keeps_health_status_and_events_are_paged(client):
    inspected = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo"},
    )
    assert inspected.status_code == 200
    issue = inspected.json()["issues"][0]
    acknowledged = client.post(
        f"/api/v1/issues/{issue['id']}/acknowledge",
        json={"note": "值班同学处理中"},
    )
    assert acknowledged.status_code == 200
    body = acknowledged.json()
    assert body["status"] == issue["status"]
    assert body["acknowledge_note"] == "值班同学处理中"

    timeline = client.get(f"/api/v1/issues/{issue['id']}/events?page=1&page_size=1")
    assert timeline.status_code == 200
    assert timeline.json()["total"] >= 2
    assert len(timeline.json()["items"]) == 1
    assert timeline.json()["items"][0]["event_type"] == "acknowledged"


def test_issue_priority_sort_is_stable_across_pages(client):
    client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"})
    first_page = client.get("/api/v1/issues?sort=priority&page=1&page_size=1")
    second_page = client.get("/api/v1/issues?sort=priority&page=2&page_size=1")
    assert first_page.status_code == second_page.status_code == 200
    first = first_page.json()
    second = second_page.json()
    assert first["total"] >= 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    assert severity_rank[first["items"][0]["severity"]] <= severity_rank[second["items"][0]["severity"]]


def test_issue_filter_options_are_generated_from_existing_issues(client):
    client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"})

    response = client.get("/api/v1/issues/filter-options")

    assert response.status_code == 200
    body = response.json()
    assert {"value": "demo", "label": "demo"} in body["namespaces"]
    assert any(option["value"] == "Pod" for option in body["resource_kinds"])
    assert any(
        option["value"] == "pod.runtime" and option["label"] == "Pod 运行状态"
        for option in body["source_checks"]
    )


def test_issue_workbench_hides_open_issues_from_previous_cluster_id(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        stale = IssueModel(
            cluster_id="previous-cluster-id",
            issue_code=IssueCode.SERVICE_NO_READY_ENDPOINT.value,
            fingerprint="f" * 64,
            severity=IssueSeverity.critical.value,
            status="open",
            scope=IssueScope.service.value,
            resource_api_version=None,
            resource_kind="Service",
            resource_namespace="platform",
            resource_name="helloworld",
            resource_uid=None,
            summary="Service helloworld 没有 Ready Endpoint",
            reason="Ready Endpoint 数量为 0。",
            suggestion="检查 Service selector、Pod Ready 和 EndpointSlice。",
            evidence=[],
            first_seen_at=now,
            last_seen_at=now,
            recovered_at=None,
            occurrence_count=1,
            source_check="service.endpoints",
            correlation_key="service:platform/helloworld",
        )
        session.add(stale)
        session.commit()
        stale_id = stale.id

    issues = client.get("/api/v1/issues?status=open")
    assert issues.status_code == 200
    assert all(item["cluster_id"] != "previous-cluster-id" for item in issues.json()["items"])
    assert all(item["resource"]["name"] != "helloworld" for item in issues.json()["items"])

    filters = client.get("/api/v1/issues/filter-options")
    assert filters.status_code == 200
    assert {"value": "platform", "label": "platform"} not in filters.json()["namespaces"]

    assert client.get(f"/api/v1/issues/{stale_id}").status_code == 404
    assert client.get(f"/api/v1/issues/{stale_id}/events").status_code == 404
    assert client.post(
        f"/api/v1/issues/{stale_id}/acknowledge",
        json={"note": "旧集群问题不能在当前集群确认"},
    ).status_code == 404

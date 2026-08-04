from datetime import datetime, timedelta, timezone

from app.models import InspectionRun as InspectionRunModel
from app.models import IssueEvent as IssueEventModel
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


def test_issue_ignore_hides_from_open_list_and_is_filterable(client):
    inspected = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo"},
    )
    assert inspected.status_code == 200
    issue = inspected.json()["issues"][0]

    ignored = client.post(f"/api/v1/issues/{issue['id']}/ignore")

    assert ignored.status_code == 200
    assert ignored.json()["status"] == "ignored"
    open_issues = client.get("/api/v1/issues?status=open")
    assert open_issues.status_code == 200
    assert all(item["id"] != issue["id"] for item in open_issues.json()["items"])
    ignored_issues = client.get("/api/v1/issues?status=ignored")
    assert ignored_issues.status_code == 200
    assert any(item["id"] == issue["id"] for item in ignored_issues.json()["items"])

    timeline = client.get(f"/api/v1/issues/{issue['id']}/events")
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["event_type"] == "ignored"

    unignored = client.post(f"/api/v1/issues/{issue['id']}/unignore")
    assert unignored.status_code == 200
    assert unignored.json()["status"] == "open"
    open_after_unignore = client.get("/api/v1/issues?status=open")
    assert any(item["id"] == issue["id"] for item in open_after_unignore.json()["items"])
    timeline = client.get(f"/api/v1/issues/{issue['id']}/events")
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["event_type"] == "unignored"


def test_issue_batch_acknowledge_ignore_and_unignore_with_partial_failure(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    scope = InspectionScope(type="namespace", namespace="demo")
    cluster_id = client.app.state.settings.cluster_id
    with session_factory() as session:
        run = _run(session, scope, now)
        opened = apply_evaluations(
            session,
            cluster_id=cluster_id,
            run_id=run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[
                _evaluation(scope, present=True),
                _service_evaluation(scope, present=True),
                _required_component_evaluation(scope, present=True),
            ],
            occurred_at=now,
        )
        session.commit()
        issue_ids = sorted(opened.issue_ids)

    acknowledged = client.post(
        "/api/v1/issues/batch/acknowledge",
        json={"issue_ids": [*issue_ids, 99999], "note": "统一备注"},
    )
    assert acknowledged.status_code == 200
    body = acknowledged.json()
    assert body["succeeded_count"] == 3
    assert body["failed_count"] == 1
    assert body["results"][-1] == {"issue_id": 99999, "succeeded": False, "issue": None, "error": "问题不存在"}
    with session_factory() as session:
        assert all(session.get(IssueModel, issue_id).acknowledge_note == "统一备注" for issue_id in issue_ids)
        assert session.query(IssueEventModel).filter(IssueEventModel.event_type == "acknowledged").count() == 3

    ignored = client.post("/api/v1/issues/batch/ignore", json={"issue_ids": issue_ids})
    assert ignored.status_code == 200
    assert ignored.json()["succeeded_count"] == 3
    assert ignored.json()["failed_count"] == 0
    open_issues = client.get("/api/v1/issues?status=open")
    assert all(item["id"] not in issue_ids for item in open_issues.json()["items"])
    ignored_issues = client.get("/api/v1/issues?status=ignored")
    assert {item["id"] for item in ignored_issues.json()["items"]} >= set(issue_ids)

    unignored = client.post("/api/v1/issues/batch/unignore", json={"issue_ids": issue_ids})
    assert unignored.status_code == 200
    assert unignored.json()["succeeded_count"] == 3
    assert unignored.json()["failed_count"] == 0
    open_after_unignore = client.get("/api/v1/issues?status=open")
    assert {item["id"] for item in open_after_unignore.json()["items"]} >= set(issue_ids)
    with session_factory() as session:
        assert session.query(IssueEventModel).filter(IssueEventModel.event_type == "ignored").count() == 3
        assert session.query(IssueEventModel).filter(IssueEventModel.event_type == "unignored").count() == 3


def test_ignored_issue_recovers_when_next_successful_check_no_longer_reports_it(client):
    session_factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    scope = InspectionScope(type="namespace", namespace="demo")
    cluster_id = client.app.state.settings.cluster_id
    with session_factory() as session:
        first_run = _run(session, scope, now)
        opened = apply_evaluations(
            session,
            cluster_id=cluster_id,
            run_id=first_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(scope, present=True)],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(opened.issue_ids))

        ignored = client.post(f"/api/v1/issues/{issue_id}/ignore")
        assert ignored.status_code == 200
        assert ignored.json()["status"] == "ignored"

        second_run = _run(session, scope, now + timedelta(minutes=1))
        recovered = apply_evaluations(
            session,
            cluster_id=cluster_id,
            run_id=second_run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[_evaluation(scope, present=False)],
            occurred_at=now + timedelta(minutes=1),
        )
        session.commit()

        assert recovered.recovered_count == 1
        assert recovered.issue_ids == {issue_id}
        row = session.get(IssueModel, issue_id)
        assert row.status == "recovered"
        event = session.query(IssueEventModel).filter_by(issue_id=issue_id).order_by(IssueEventModel.id.desc()).first()
        assert event.event_type == "recovered"
        assert event.previous_status == "ignored"

    ignored_list = client.get("/api/v1/issues?status=ignored")
    assert ignored_list.status_code == 200
    assert all(item["id"] != issue_id for item in ignored_list.json()["items"])
    recovered_list = client.get("/api/v1/issues?status=recovered")
    assert recovered_list.status_code == 200
    assert any(item["id"] == issue_id for item in recovered_list.json()["items"])


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


def test_issue_api_keeps_v1_1_response_fields(client):
    inspected = client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"})
    assert inspected.status_code == 200
    issue_id = inspected.json()["issues"][0]["id"]

    response = client.get(f"/api/v1/issues/{issue_id}")

    assert response.status_code == 200
    body = response.json()
    assert {
        "id",
        "cluster_id",
        "issue_code",
        "fingerprint",
        "severity",
        "status",
        "scope",
        "resource",
        "summary",
        "reason",
        "suggestion",
        "evidence",
        "first_seen_at",
        "last_seen_at",
        "recovered_at",
        "occurrence_count",
        "source_check",
        "correlation_key",
        "acknowledged_at",
        "acknowledge_note",
    }.issubset(body)
    assert {"api_version", "kind", "namespace", "name", "uid"}.issubset(body["resource"])


def test_issue_note_can_be_added_listed_redacted_and_does_not_change_status(client):
    inspected = client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"})
    assert inspected.status_code == 200
    issue_id = inspected.json()["issues"][0]["id"]

    first = client.post(
        f"/api/v1/issues/{issue_id}/notes",
        json={"content": "已联系业务，token=abc123 password=secret-value"},
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["event_type"] == "note_added"
    assert first_body["actor"] == "development"
    assert first_body["previous_status"] == "open"
    assert first_body["new_status"] == "open"
    assert "abc123" not in first_body["summary"]
    assert "secret-value" not in first_body["summary"]
    assert "token=[REDACTED]" in first_body["summary"]
    assert "password=[REDACTED]" in first_body["summary"]

    second = client.post(
        f"/api/v1/issues/{issue_id}/notes",
        json={"content": "二线处理中"},
    )
    assert second.status_code == 201

    issue = client.get(f"/api/v1/issues/{issue_id}")
    assert issue.status_code == 200
    assert issue.json()["status"] == "open"
    assert issue.json()["acknowledged_at"] is None

    events = client.get(f"/api/v1/issues/{issue_id}/events")
    assert events.status_code == 200
    note_events = [item for item in events.json()["items"] if item["event_type"] == "note_added"]
    assert note_events[0]["summary"] == "二线处理中"
    assert note_events[1]["summary"].startswith("已联系业务")
    assert "abc123" not in note_events[1]["summary"]
    assert "secret-value" not in note_events[1]["summary"]


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

"""End-to-end security gates for public evidence and failure text."""

from datetime import datetime, timezone

from app.models import InspectionCheckResult as InspectionCheckResultModel
from app.models import InspectionRun as InspectionRunModel
from app.models import Issue as IssueModel
from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    CollectionLayer,
    Coverage,
    Evidence,
    InspectionScope,
    InspectionTrigger,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    NotificationEventType,
    ProviderCollectionFailure,
    ProviderCollectionResult,
    ResourceRef,
    build_inspection_scope_key,
)
from app.services.inspection_run_service import execute_inspection
from app.services.issue_lifecycle import apply_evaluations
from app.services.notification_adapter import build_generic_payload
from app.services.notification_service import _issue_message


SENSITIVE = (
    "ERROR upstream unavailable; password=plain-password "
    "token=secret-token "
    "https://open.feishu.cn/open-apis/bot/v2/hook/webhook-secret"
)
FORBIDDEN = ("plain-password", "secret-token", "webhook-secret")


def _assert_safe(payload) -> None:
    serialized = str(payload)
    assert "ERROR upstream unavailable" in serialized
    assert all(secret not in serialized for secret in FORBIDDEN)


def test_issue_create_get_list_timeline_notification_and_sqlite_are_safe(
    client,
    test_settings,
) -> None:
    now = datetime.now(timezone.utc)
    scope = InspectionScope(type="namespace", namespace="demo")
    candidate = IssueCandidate(
        issue_code=IssueCode.POD_WARNING_EVENT,
        severity=IssueSeverity.warning,
        scope=IssueScope.pod,
        resource=ResourceRef(kind="Pod", namespace="demo", name="api-0"),
        summary=f"Pod warning: {SENSITIVE}",
        reason=f"Event reason: {SENSITIVE}",
        suggestion=f"Check event: {SENSITIVE}",
        evidence=[
            Evidence(
                code="pod.warning_event",
                source="event",
                summary=f"Warning Event: {SENSITIVE}",
                facts={
                    "event_message": SENSITIVE,
                    "failure_reason": SENSITIVE,
                    "safe_fact": "ERROR upstream unavailable",
                },
                observed_at=now,
            )
        ],
        source_check="pod.runtime",
    )
    evaluation = CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code="pod.runtime",
            name="Pod runtime",
            status=CheckStatus.abnormal,
            reason="发现异常",
            checked_objects=1,
            duration_ms=1,
            issue_count=1,
        ),
        issue_candidates=[candidate],
    )

    with client.app.state.session_factory() as session:
        run = InspectionRunModel(
            trigger="manual",
            status="running",
            scope=scope.model_dump(mode="json"),
            started_at=now,
            coverage=[],
        )
        session.add(run)
        session.commit()
        lifecycle = apply_evaluations(
            session,
            cluster_id="cluster-sensitive",
            run_id=run.id,
            trigger=InspectionTrigger.manual,
            evaluations=[evaluation],
            occurred_at=now,
        )
        session.commit()
        issue_id = next(iter(lifecycle.issue_ids))
        row = session.get(IssueModel, issue_id)
        sqlite_payload = {
            "summary": row.summary,
            "reason": row.reason,
            "suggestion": row.suggestion,
            "evidence": row.evidence,
        }
        notification = build_generic_payload(
            _issue_message(
                test_settings,
                row,
                NotificationEventType.issue_opened,
            )
        )

    responses = [
        client.get(f"/api/v1/issues/{issue_id}"),
        client.get("/api/v1/issues"),
        client.get(f"/api/v1/issues/{issue_id}/events"),
    ]
    assert all(response.status_code == 200 for response in responses)
    _assert_safe(
        {
            "issue_get": responses[0].json(),
            "issue_list": responses[1].json(),
            "timeline": responses[2].json(),
            "notification": notification,
            "sqlite": sqlite_payload,
        }
    )


class SensitiveFailureProvider:
    def collect_resources(self, request) -> ProviderCollectionResult:
        return ProviderCollectionResult(
            layer=CollectionLayer.status,
            failures=[
                ProviderCollectionFailure(
                    check_code="pod.runtime",
                    error_code="KUBERNETES_API_ERROR",
                    message=SENSITIVE,
                )
            ],
            kubernetes_api_calls=1,
        )


def test_provider_failure_reason_run_api_and_sqlite_are_safe(client) -> None:
    with client.app.state.session_factory() as session:
        run, _ = execute_inspection(
            session,
            provider=SensitiveFailureProvider(),
            cluster_id="cluster-sensitive",
            scope=InspectionScope(type="namespace", namespace="demo"),
            trigger=InspectionTrigger.manual,
        )
        run_id = run.id
        row = session.get(InspectionRunModel, run_id)
        checks = session.query(InspectionCheckResultModel).filter_by(
            run_id=run_id
        ).all()
        sqlite_payload = {
            "coverage": row.coverage,
            "error_message": row.error_message,
            "check_results": [
                {
                    "name": check.name,
                    "reason": check.reason,
                }
                for check in checks
            ],
        }

    detail = client.get(f"/api/v1/inspection-runs/{run_id}")
    listing = client.get("/api/v1/inspection-runs")
    assert detail.status_code == listing.status_code == 200
    _assert_safe(
        {
            "run_detail": detail.json(),
            "run_list": listing.json(),
            "sqlite": sqlite_payload,
        }
    )

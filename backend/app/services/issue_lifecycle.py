from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Issue as IssueModel
from app.models import IssueEvent as IssueEventModel
from app.models import IssueScopeMembership
from app.models.v1_1 import inspection_run_issues
from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    InspectionTrigger,
    IssueAcknowledgeRequest,
    IssueCandidate,
    IssueEventType,
    IssueSeverity,
    IssueStatus,
    build_issue_fingerprint,
)
from app.services.issue_query import issue_from_model
from app.services.payload_sanitizer import sanitize_public_payload


_SEVERITY_RANK = {
    IssueSeverity.info.value: 0,
    IssueSeverity.warning.value: 1,
    IssueSeverity.critical.value: 2,
}


@dataclass
class LifecycleChange:
    issue: IssueModel
    event: IssueEventModel


@dataclass
class LifecycleResult:
    issue_ids: set[int] = field(default_factory=set)
    opened_count: int = 0
    recovered_count: int = 0
    changes: list[LifecycleChange] = field(default_factory=list)


def apply_evaluations(
    session: Session,
    *,
    cluster_id: str,
    run_id: int,
    trigger: InspectionTrigger,
    evaluations: list[CheckEvaluation],
    occurred_at: datetime | None = None,
) -> LifecycleResult:
    now = occurred_at or datetime.now(timezone.utc)
    result = LifecycleResult()
    seen_evaluations: set[tuple[str, str]] = set()

    for evaluation in evaluations:
        identity = (evaluation.coverage.check_code, evaluation.scope_key)
        if identity in seen_evaluations:
            raise ValueError("同一次运行不能重复提交相同 check_code 和 scope_key")
        seen_evaluations.add(identity)
        if evaluation.coverage.status in {CheckStatus.failed, CheckStatus.skipped}:
            continue

        current_fingerprints: set[str] = set()
        for candidate in evaluation.issue_candidates:
            candidate = IssueCandidate.model_validate(
                sanitize_public_payload(candidate.model_dump(mode="json"))
            )
            fingerprint = build_issue_fingerprint(
                cluster_id=cluster_id,
                source_check=candidate.source_check,
                issue_code=candidate.issue_code,
                resource=candidate.resource,
            )
            current_fingerprints.add(fingerprint)
            row, change = _observe_candidate(
                session,
                cluster_id=cluster_id,
                run_id=run_id,
                trigger=trigger,
                candidate=candidate,
                fingerprint=fingerprint,
                occurred_at=now,
            )
            session.flush()
            _activate_membership(
                session,
                issue_id=row.id,
                scope_key=evaluation.scope_key,
                run_id=run_id,
                occurred_at=now,
            )
            _link_run_issue(session, run_id=run_id, issue_id=row.id)
            result.issue_ids.add(row.id)
            if change is not None:
                result.changes.append(change)
                if change.event.event_type in {
                    IssueEventType.opened.value,
                    IssueEventType.reopened.value,
                }:
                    result.opened_count += 1

        recovered = _recover_missing(
            session,
            cluster_id=cluster_id,
            source_check=evaluation.coverage.check_code,
            scope_key=evaluation.scope_key,
            run_id=run_id,
            trigger=trigger,
            current_fingerprints=current_fingerprints,
            occurred_at=now,
        )
        result.recovered_count += len(recovered)
        for change in recovered:
            session.flush()
            _link_run_issue(session, run_id=run_id, issue_id=change.issue.id)
            result.issue_ids.add(change.issue.id)
        result.changes.extend(recovered)

    session.flush()
    return result


def acknowledge_issue(
    session: Session,
    *,
    issue_id: int,
    payload: IssueAcknowledgeRequest,
    trigger: InspectionTrigger = InspectionTrigger.manual,
    occurred_at: datetime | None = None,
):
    row = session.get(IssueModel, issue_id)
    if row is None:
        return None
    now = occurred_at or datetime.now(timezone.utc)
    row.acknowledged_at = now
    row.acknowledge_note = sanitize_public_payload(payload.note)
    event = IssueEventModel(
        issue_id=row.id,
        event_type=IssueEventType.acknowledged.value,
        trigger=trigger.value,
        previous_status=row.status,
        new_status=row.status,
        previous_severity=row.severity,
        new_severity=row.severity,
        occurred_at=now,
        summary="问题已确认；确认不改变实际健康状态",
        evidence_codes=[],
    )
    session.add(event)
    session.commit()
    session.refresh(row)
    return issue_from_model(row)


def _observe_candidate(
    session: Session,
    *,
    cluster_id: str,
    run_id: int,
    trigger: InspectionTrigger,
    candidate: IssueCandidate,
    fingerprint: str,
    occurred_at: datetime,
) -> tuple[IssueModel, LifecycleChange | None]:
    row = session.scalar(
        select(IssueModel).where(
            IssueModel.cluster_id == cluster_id,
            IssueModel.fingerprint == fingerprint,
        )
    )
    evidence = [item.model_dump(mode="json") for item in candidate.evidence]
    evidence_codes = [item.code for item in candidate.evidence]
    if row is None:
        row = IssueModel(
            cluster_id=cluster_id,
            fingerprint=fingerprint,
            issue_code=candidate.issue_code.value,
            severity=candidate.severity.value,
            status=IssueStatus.open.value,
            scope=candidate.scope.value,
            resource_api_version=candidate.resource.api_version,
            resource_kind=candidate.resource.kind,
            resource_namespace=candidate.resource.namespace,
            resource_name=candidate.resource.name,
            resource_uid=candidate.resource.uid,
            summary=candidate.summary,
            reason=candidate.reason,
            suggestion=candidate.suggestion,
            evidence=evidence,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
            recovered_at=None,
            occurrence_count=1,
            source_check=candidate.source_check,
            correlation_key=candidate.correlation_key,
        )
        session.add(row)
        session.flush()
        event = _event(
            row,
            run_id=run_id,
            event_type=IssueEventType.opened,
            trigger=trigger,
            previous_status=None,
            new_status=IssueStatus.open,
            previous_severity=None,
            new_severity=candidate.severity,
            occurred_at=occurred_at,
            summary="首次发现问题",
            evidence_codes=evidence_codes,
        )
        session.add(event)
        return row, LifecycleChange(row, event)

    previous_status = IssueStatus(row.status)
    previous_severity = IssueSeverity(row.severity)
    reopened = previous_status == IssueStatus.recovered
    escalated = _SEVERITY_RANK[candidate.severity.value] > _SEVERITY_RANK[previous_severity.value]
    row.issue_code = candidate.issue_code.value
    row.severity = candidate.severity.value
    row.status = IssueStatus.open.value
    row.scope = candidate.scope.value
    row.resource_api_version = candidate.resource.api_version
    row.resource_kind = candidate.resource.kind
    row.resource_namespace = candidate.resource.namespace
    row.resource_name = candidate.resource.name
    row.resource_uid = candidate.resource.uid
    row.summary = candidate.summary
    row.reason = candidate.reason
    row.suggestion = candidate.suggestion
    row.evidence = evidence
    row.last_seen_at = max(_aware(row.last_seen_at), occurred_at)
    row.recovered_at = None
    row.occurrence_count += 1
    row.source_check = candidate.source_check
    row.correlation_key = candidate.correlation_key

    event_type = (
        IssueEventType.reopened
        if reopened
        else IssueEventType.severity_escalated
        if escalated
        else IssueEventType.observed
    )
    summary = (
        "问题再次出现"
        if reopened
        else "问题严重程度升级"
        if escalated
        else "本轮仍观察到问题"
    )
    event = _event(
        row,
        run_id=run_id,
        event_type=event_type,
        trigger=trigger,
        previous_status=previous_status,
        new_status=IssueStatus.open,
        previous_severity=previous_severity,
        new_severity=candidate.severity,
        occurred_at=occurred_at,
        summary=summary,
        evidence_codes=evidence_codes,
    )
    session.add(event)
    return row, LifecycleChange(row, event)


def _recover_missing(
    session: Session,
    *,
    cluster_id: str,
    source_check: str,
    scope_key: str,
    run_id: int,
    trigger: InspectionTrigger,
    current_fingerprints: set[str],
    occurred_at: datetime,
) -> list[LifecycleChange]:
    query = (
        select(IssueModel, IssueScopeMembership)
        .join(IssueScopeMembership, IssueScopeMembership.issue_id == IssueModel.id)
        .where(
        IssueModel.cluster_id == cluster_id,
        IssueModel.source_check == source_check,
        IssueModel.status == IssueStatus.open.value,
            IssueScopeMembership.scope_key == scope_key,
            IssueScopeMembership.active.is_(True),
        )
    )
    if current_fingerprints:
        query = query.where(IssueModel.fingerprint.not_in(current_fingerprints))
    changes: list[LifecycleChange] = []
    for row, membership in session.execute(query).all():
        membership.active = False
        membership.deactivated_at = occurred_at
        session.flush()
        remaining_active = session.scalar(
            select(IssueScopeMembership.issue_id)
            .where(
                IssueScopeMembership.issue_id == row.id,
                IssueScopeMembership.active.is_(True),
            )
            .limit(1)
        )
        if remaining_active is not None:
            continue
        row.status = IssueStatus.recovered.value
        row.recovered_at = max(_aware(row.last_seen_at), occurred_at)
        event = _event(
            row,
            run_id=run_id,
            event_type=IssueEventType.recovered,
            trigger=trigger,
            previous_status=IssueStatus.open,
            new_status=IssueStatus.recovered,
            previous_severity=IssueSeverity(row.severity),
            new_severity=IssueSeverity(row.severity),
            occurred_at=row.recovered_at,
            summary="本轮检查成功且问题已不再出现",
            evidence_codes=[],
        )
        session.add(event)
        changes.append(LifecycleChange(row, event))
    return changes


def _activate_membership(
    session: Session,
    *,
    issue_id: int,
    scope_key: str,
    run_id: int,
    occurred_at: datetime,
) -> None:
    membership = session.get(
        IssueScopeMembership,
        {"issue_id": issue_id, "scope_key": scope_key},
    )
    if membership is None:
        membership = IssueScopeMembership(
            issue_id=issue_id,
            scope_key=scope_key,
            active=True,
            last_seen_run_id=run_id,
            last_seen_at=occurred_at,
            deactivated_at=None,
        )
        session.add(membership)
    else:
        membership.active = True
        membership.last_seen_run_id = run_id
        membership.last_seen_at = occurred_at
        membership.deactivated_at = None
    session.flush()


def _event(
    row: IssueModel,
    *,
    run_id: int | None,
    event_type: IssueEventType,
    trigger: InspectionTrigger,
    previous_status: IssueStatus | None,
    new_status: IssueStatus | None,
    previous_severity: IssueSeverity | None,
    new_severity: IssueSeverity | None,
    occurred_at: datetime,
    summary: str,
    evidence_codes: list[str],
) -> IssueEventModel:
    return IssueEventModel(
        issue_id=row.id,
        run_id=run_id,
        event_type=event_type.value,
        trigger=trigger.value,
        previous_status=previous_status.value if previous_status else None,
        new_status=new_status.value if new_status else None,
        previous_severity=previous_severity.value if previous_severity else None,
        new_severity=new_severity.value if new_severity else None,
        occurred_at=occurred_at,
        summary=summary,
        evidence_codes=evidence_codes,
    )


def _link_run_issue(session: Session, *, run_id: int, issue_id: int) -> None:
    exists = session.execute(
        select(inspection_run_issues.c.issue_id).where(
            inspection_run_issues.c.run_id == run_id,
            inspection_run_issues.c.issue_id == issue_id,
        )
    ).first()
    if exists is None:
        session.execute(inspection_run_issues.insert().values(run_id=run_id, issue_id=issue_id))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

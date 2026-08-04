from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.models import Issue as IssueModel
from app.models import IssueEvent as IssueEventModel
from app.schemas.v1_1 import (
    Evidence,
    InspectionTrigger,
    Issue,
    IssueEvent,
    IssueEventType,
    IssueFilterOption,
    IssueFilterOptions,
    IssueListFilter,
    IssueScope,
    IssueSeverity,
    IssueSortMode,
    IssueStatus,
    Page,
    ResourceRef,
)
from app.services.payload_sanitizer import sanitize_public_payload


_RESOURCE_KIND_LABELS = {
    "CronJob": "定时任务（CronJob）",
    "DaemonSet": "守护进程（DaemonSet）",
    "Deployment": "应用部署（Deployment）",
    "Ingress": "访问入口（Ingress）",
    "Job": "任务（Job）",
    "Node": "节点（Node）",
    "PersistentVolume": "持久卷（PV）",
    "PersistentVolumeClaim": "持久卷声明（PVC）",
    "Pod": "容器实例（Pod）",
    "Service": "服务（Service）",
    "StatefulSet": "有状态应用（StatefulSet）",
    "TLSSecret": "TLS 证书 Secret",
}

_SOURCE_CHECK_LABELS = {
    "ingress.config_chain": "Ingress 配置链路",
    "kubernetes.version": "Kubernetes 版本",
    "metrics.resource": "CPU 与内存指标",
    "node.health": "节点健康",
    "pod.runtime": "Pod 运行状态",
    "required_components": "必需组件",
    "service.endpoints": "Service 后端",
    "storage.status": "存储状态",
    "tls.certificate": "TLS 证书",
    "workload.status": "工作负载状态",
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def issue_from_model(row: IssueModel) -> Issue:
    payload = {
        "id": row.id,
        "cluster_id": row.cluster_id,
        "issue_code": row.issue_code,
        "fingerprint": row.fingerprint,
        "severity": row.severity,
        "status": row.status,
        "scope": row.scope,
        "resource": {
            "api_version": row.resource_api_version,
            "kind": row.resource_kind,
            "namespace": row.resource_namespace,
            "name": row.resource_name,
            "uid": row.resource_uid,
        },
        "summary": row.summary,
        "reason": row.reason,
        "suggestion": row.suggestion,
        "evidence": list(row.evidence or []),
        "first_seen_at": _utc(row.first_seen_at),
        "last_seen_at": _utc(row.last_seen_at),
        "recovered_at": _utc(row.recovered_at),
        "occurrence_count": row.occurrence_count,
        "source_check": row.source_check,
        "correlation_key": row.correlation_key,
        "acknowledged_at": _utc(row.acknowledged_at),
        "acknowledge_note": row.acknowledge_note,
    }
    return Issue.model_validate(sanitize_public_payload(payload))


def issue_event_from_model(row: IssueEventModel) -> IssueEvent:
    payload = {
        "id": row.id,
        "issue_id": row.issue_id,
        "run_id": row.run_id,
        "event_type": row.event_type,
        "trigger": row.trigger,
        "previous_status": row.previous_status,
        "new_status": row.new_status,
        "previous_severity": row.previous_severity,
        "new_severity": row.new_severity,
        "occurred_at": _utc(row.occurred_at),
        "summary": row.summary,
        "actor": row.actor,
        "evidence_codes": list(row.evidence_codes or []),
    }
    return IssueEvent.model_validate(sanitize_public_payload(payload))


def get_issue(session: Session, issue_id: int, *, cluster_id: str | None = None) -> IssueModel | None:
    row = session.get(IssueModel, issue_id)
    if row is None:
        return None
    if cluster_id is not None and row.cluster_id != cluster_id:
        return None
    return row


def list_issue_filter_options(session: Session, *, cluster_id: str | None = None) -> IssueFilterOptions:
    namespace_query = select(IssueModel.resource_namespace).where(IssueModel.resource_namespace.is_not(None))
    resource_kind_query = select(IssueModel.resource_kind)
    source_check_query = select(IssueModel.source_check)
    if cluster_id is not None:
        namespace_query = namespace_query.where(IssueModel.cluster_id == cluster_id)
        resource_kind_query = resource_kind_query.where(IssueModel.cluster_id == cluster_id)
        source_check_query = source_check_query.where(IssueModel.cluster_id == cluster_id)
    namespaces = session.scalars(
        namespace_query
        .distinct()
        .order_by(IssueModel.resource_namespace)
    ).all()
    resource_kinds = session.scalars(
        resource_kind_query.distinct().order_by(IssueModel.resource_kind)
    ).all()
    source_checks = session.scalars(
        source_check_query.distinct().order_by(IssueModel.source_check)
    ).all()
    return IssueFilterOptions(
        namespaces=[
            IssueFilterOption(value=value, label=value)
            for value in namespaces
            if value
        ],
        resource_kinds=[
            IssueFilterOption(
                value=value,
                label=_RESOURCE_KIND_LABELS.get(value, value),
            )
            for value in resource_kinds
            if value
        ],
        source_checks=[
            IssueFilterOption(
                value=value,
                label=_SOURCE_CHECK_LABELS.get(value, value),
            )
            for value in source_checks
            if value
        ],
    )


def list_issues(session: Session, filters: IssueListFilter, *, cluster_id: str | None = None) -> Page[Issue]:
    query = select(IssueModel)
    if cluster_id is not None:
        query = query.where(IssueModel.cluster_id == cluster_id)
    if filters.status is not None:
        query = query.where(IssueModel.status == filters.status.value)
    if filters.severity is not None:
        query = query.where(IssueModel.severity == filters.severity.value)
    if filters.namespace is not None:
        query = query.where(IssueModel.resource_namespace == filters.namespace)
    if filters.resource_kind is not None:
        query = query.where(func.lower(IssueModel.resource_kind) == filters.resource_kind.casefold())
    if filters.source_check is not None:
        query = query.where(IssueModel.source_check == filters.source_check)

    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    query_time = datetime.now(timezone.utc)
    status_rank = case(
        (IssueModel.status == IssueStatus.open.value, 0),
        (IssueModel.status == IssueStatus.ignored.value, 1),
        else_=2,
    )
    severity_rank = case(
        (IssueModel.severity == IssueSeverity.critical.value, 0),
        (IssueModel.severity == IssueSeverity.warning.value, 1),
        else_=2,
    )
    duration = case(
        (
            IssueModel.status.in_([IssueStatus.open.value, IssueStatus.ignored.value]),
            func.julianday(query_time) - func.julianday(IssueModel.first_seen_at),
        ),
        else_=func.julianday(IssueModel.recovered_at) - func.julianday(IssueModel.first_seen_at),
    )
    if filters.sort == IssueSortMode.last_changed:
        latest_event = (
            select(func.max(IssueEventModel.occurred_at))
            .where(IssueEventModel.issue_id == IssueModel.id)
            .correlate(IssueModel)
            .scalar_subquery()
        )
        query = query.order_by(desc(func.coalesce(latest_event, IssueModel.first_seen_at)), desc(IssueModel.id))
    elif filters.sort == IssueSortMode.duration:
        query = query.order_by(status_rank, desc(duration), severity_rank, desc(IssueModel.id))
    else:
        query = query.order_by(status_rank, severity_rank, desc(duration), desc(IssueModel.id))

    rows = session.scalars(
        query.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
    ).all()
    return Page[Issue](
        items=[issue_from_model(row) for row in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def list_issue_events(
    session: Session,
    *,
    issue_id: int,
    page: int,
    page_size: int,
    cluster_id: str | None = None,
) -> Page[IssueEvent] | None:
    if get_issue(session, issue_id, cluster_id=cluster_id) is None:
        return None
    base = select(IssueEventModel).where(IssueEventModel.issue_id == issue_id)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.scalars(
        base.order_by(desc(IssueEventModel.occurred_at), desc(IssueEventModel.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[IssueEvent](
        items=[issue_event_from_model(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )

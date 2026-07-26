from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    InspectionCheckResult as InspectionCheckResultModel,
    InspectionRun as InspectionRunModel,
    ResourceMetricState as ResourceMetricStateModel,
    SystemSetting,
)
from app.models.v1_1 import inspection_run_issues
from app.providers.base import InspectionProvider
from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    CollectionLayer,
    CollectionLimits,
    ComponentState,
    Coverage,
    InspectionCheckResult,
    InspectionPolicySettings,
    InspectionRun,
    InspectionRunDetail,
    InspectionRunListFilter,
    InspectionRunStatus,
    InspectionScope,
    InspectionScopeType,
    InspectionTrigger,
    Page,
    ProviderCollectionRequest,
    ProviderCollectionResult,
    ProviderObservation,
    ResourceRef,
    SystemComponentStatus,
    build_inspection_scope_key,
)
from app.schemas.diagnosis import DiagnosisRequest
from app.security.component_status import ComponentStatusRegistry
from app.services.issue_lifecycle import LifecycleResult, apply_evaluations
from app.services.resource_inspection import evaluate_resource_collection
from app.services import diagnosis_service
from app.services.payload_sanitizer import sanitize_public_payload


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_from_model(session: Session, row: InspectionRunModel) -> InspectionRun:
    issue_ids = list(
        session.scalars(
            select(inspection_run_issues.c.issue_id)
            .where(inspection_run_issues.c.run_id == row.id)
            .order_by(inspection_run_issues.c.issue_id)
        ).all()
    )
    return InspectionRun(
        id=row.id,
        plan_id=row.plan_id,
        inspection_record_id=row.inspection_record_id,
        trigger=row.trigger,
        status=row.status,
        scope=InspectionScope.model_validate(row.scope),
        started_at=_utc(row.started_at),
        finished_at=_utc(row.finished_at),
        coverage=sanitize_public_payload(list(row.coverage or [])),
        issue_ids=issue_ids,
        opened_issue_count=row.opened_issue_count,
        recovered_issue_count=row.recovered_issue_count,
        kubernetes_api_calls=row.kubernetes_api_calls,
        log_pods_read=row.log_pods_read,
        collected_log_bytes=row.collected_log_bytes,
        duration_ms=row.duration_ms,
        error_code=row.error_code,
        error_message=sanitize_public_payload(row.error_message),
    )


def check_result_from_model(row: InspectionCheckResultModel) -> InspectionCheckResult:
    return InspectionCheckResult(
        id=row.id,
        run_id=row.run_id,
        check_code=row.check_code,
        name=sanitize_public_payload(row.name),
        status=row.status,
        reason=sanitize_public_payload(row.reason),
        checked_objects=row.checked_objects,
        duration_ms=row.duration_ms,
        issue_count=row.issue_count,
        scope=InspectionScope.model_validate(row.scope),
        scope_key=row.scope_key,
        completed_at=_utc(row.completed_at),
    )


def get_run(session: Session, run_id: int) -> InspectionRunDetail | None:
    row = session.get(InspectionRunModel, run_id)
    if row is None:
        return None
    checks = session.scalars(
        select(InspectionCheckResultModel)
        .where(InspectionCheckResultModel.run_id == run_id)
        .order_by(InspectionCheckResultModel.id)
    ).all()
    return InspectionRunDetail(
        **run_from_model(session, row).model_dump(),
        check_results=[check_result_from_model(item) for item in checks],
    )


def list_runs(session: Session, filters: InspectionRunListFilter) -> Page[InspectionRun]:
    query = select(InspectionRunModel)
    if filters.status is not None:
        query = query.where(InspectionRunModel.status == filters.status.value)
    if filters.trigger is not None:
        query = query.where(InspectionRunModel.trigger == filters.trigger.value)
    if filters.plan_id is not None:
        query = query.where(InspectionRunModel.plan_id == filters.plan_id)
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = session.scalars(
        query.order_by(desc(InspectionRunModel.created_at), desc(InspectionRunModel.id))
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()
    return Page[InspectionRun](
        items=[run_from_model(session, row) for row in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def execute_inspection(
    session: Session,
    *,
    provider: InspectionProvider,
    cluster_id: str,
    scope: InspectionScope,
    trigger: InspectionTrigger,
    plan_id: int | None = None,
    inspection_record_id: int | None = None,
    registry: ComponentStatusRegistry | None = None,
    existing_run_id: int | None = None,
    include_template_matching: bool = False,
    provider_mode: str | None = None,
) -> tuple[InspectionRun, LifecycleResult]:
    started_at = utcnow()
    if existing_run_id is not None:
        run = session.get(InspectionRunModel, existing_run_id)
        if run is None:
            raise LookupError("待执行的巡检记录不存在")
        if run.status != InspectionRunStatus.queued.value:
            raise ValueError("只有 queued 巡检可以被后台执行器接管")
        if InspectionScope.model_validate(run.scope) != scope:
            raise ValueError("queued 巡检范围与执行请求不一致")
        run.status = InspectionRunStatus.running.value
        run.started_at = started_at
        run.error_code = None
        run.error_message = None
    else:
        run = InspectionRunModel(
            plan_id=plan_id,
            inspection_record_id=inspection_record_id,
            trigger=trigger.value,
            status=InspectionRunStatus.running.value,
            scope=scope.model_dump(mode="json"),
            started_at=started_at,
            coverage=[],
        )
        session.add(run)
    session.commit()
    session.refresh(run)

    try:
        policy = _load_policy_snapshot(session)
        limits = CollectionLimits(
            max_log_pods=policy.max_log_pods,
            namespace_concurrency=policy.namespace_concurrency,
        )
        collections = _collect_status(
            provider,
            scope=scope,
            trigger=trigger,
            policy=policy,
            limits=limits,
        )
        _update_kubernetes_registry(
            registry,
            provider_mode=provider_mode
            or getattr(getattr(provider, "settings", None), "provider_mode", "mock"),
            collections=collections,
        )
        evaluations: list[CheckEvaluation] = []
        api_calls = log_pods = log_bytes = 0
        for actual_scope, collected in collections:
            scope_failure = next(
                (
                    item
                    for item in collected.failures
                    if item.check_code == "inspection.scope"
                ),
                None,
            )
            if scope_failure is not None:
                evaluations.append(
                    CheckEvaluation(
                        scope=actual_scope,
                        scope_key=build_inspection_scope_key(actual_scope),
                        coverage=Coverage(
                            check_code="inspection.scope",
                            name="名称空间采集",
                            status=CheckStatus.failed,
                            reason=scope_failure.message,
                            checked_objects=0,
                            duration_ms=collected.duration_ms,
                            issue_count=0,
                        ),
                        issue_candidates=[],
                    )
                )
                continue
            enriched = _enrich_metric_state(
                session,
                cluster_id=cluster_id,
                result=collected,
                policy=policy,
                trigger=trigger,
            )
            evaluations.extend(
                evaluate_resource_collection(
                    enriched,
                    scope=actual_scope,
                    policy=policy,
                    trigger=trigger,
                    now=started_at,
                )
            )
            api_calls += collected.kubernetes_api_calls
            log_pods += collected.log_pods_read
            log_bytes += collected.collected_log_bytes

        if include_template_matching:
            evaluations.append(
                _evaluate_templates(
                    session,
                    provider=provider,
                    scope=scope,
                )
            )

        _persist_check_results(session, run_id=run.id, evaluations=evaluations)
        lifecycle = apply_evaluations(
            session,
            cluster_id=cluster_id,
            run_id=run.id,
            trigger=trigger,
            evaluations=evaluations,
            occurred_at=utcnow(),
        )
        finished_at = utcnow()
        statuses = [item.coverage.status for item in evaluations]
        run_status = _aggregate_run_status(statuses)
        run.status = run_status.value
        run.finished_at = finished_at
        run.coverage = sanitize_public_payload(
            [
                item.model_dump(mode="json")
                for item in _aggregate_coverage(evaluations)
            ]
        )
        run.opened_issue_count = lifecycle.opened_count
        run.recovered_issue_count = lifecycle.recovered_count
        run.kubernetes_api_calls = api_calls
        run.log_pods_read = log_pods
        run.collected_log_bytes = log_bytes
        run.duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        if run_status == InspectionRunStatus.failed:
            run.error_code = "INSPECTION_ALL_CHECKS_FAILED"
            run.error_message = "巡检未完成任何有效检查，请查看 scoped check_results"
        session.commit()
        session.refresh(run)
        _update_registry(registry, run)
        return run_from_model(session, run), lifecycle
    except Exception as exc:
        session.rollback()
        failed = session.get(InspectionRunModel, run.id)
        if failed is None:
            raise
        finished_at = utcnow()
        failed.status = InspectionRunStatus.failed.value
        failed.finished_at = finished_at
        failed.duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        failed.error_code = "INSPECTION_EXECUTION_FAILED"
        failed.error_message = f"巡检执行失败：{type(exc).__name__}"
        session.commit()
        session.refresh(failed)
        _update_registry(registry, failed)
        return run_from_model(session, failed), LifecycleResult()


def _collect_status(
    provider: InspectionProvider,
    *,
    scope: InspectionScope,
    trigger: InspectionTrigger,
    policy: InspectionPolicySettings,
    limits: CollectionLimits,
) -> list[tuple[InspectionScope, ProviderCollectionResult]]:
    if scope.type != InspectionScopeType.namespace or not scope.namespaces:
        request = ProviderCollectionRequest(
            scope=scope,
            layer=CollectionLayer.status,
            thresholds=policy.thresholds,
            trigger=trigger,
            limits=limits,
        )
        return [(scope, provider.collect_resources(request))]

    scopes = [
        InspectionScope(type=InspectionScopeType.namespace, namespace=namespace)
        for namespace in scope.namespaces
    ]
    results: dict[str, ProviderCollectionResult] = {}
    with ThreadPoolExecutor(max_workers=limits.namespace_concurrency) as executor:
        futures = {
            executor.submit(
                provider.collect_resources,
                ProviderCollectionRequest(
                    scope=item,
                    layer=CollectionLayer.status,
                    thresholds=policy.thresholds,
                    trigger=trigger,
                    limits=limits,
                ),
            ): item
            for item in scopes
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                results[item.namespace or ""] = future.result()
            except Exception as exc:
                results[item.namespace or ""] = ProviderCollectionResult(
                    layer=CollectionLayer.status,
                    failures=[
                        {
                            "check_code": "inspection.scope",
                            "error_code": "NAMESPACE_COLLECTION_FAILED",
                            "message": f"名称空间采集失败：{type(exc).__name__}",
                            "resource": ResourceRef(kind="Namespace", name=item.namespace or ""),
                            "retryable": True,
                        }
                    ],
                )
    return [(item, results[item.namespace or ""]) for item in scopes]


def _load_policy_snapshot(session: Session) -> InspectionPolicySettings:
    row = session.get(SystemSetting, 1)
    if row is None or not row.inspection_policy:
        return InspectionPolicySettings()
    return InspectionPolicySettings.model_validate(row.inspection_policy)


def _enrich_metric_state(
    session: Session,
    *,
    cluster_id: str,
    result: ProviderCollectionResult,
    policy: InspectionPolicySettings,
    trigger: InspectionTrigger,
) -> ProviderCollectionResult:
    enriched: list[ProviderObservation] = []
    threshold = policy.thresholds.resource_usage_warning_percent
    for observation in result.observations:
        if observation.resource.kind not in {"PodMetric", "NodeMetric"}:
            enriched.append(observation)
            continue
        namespace = observation.resource.namespace or ""
        container_name = ""
        state = session.scalar(
            select(ResourceMetricStateModel).where(
                ResourceMetricStateModel.cluster_id == cluster_id,
                ResourceMetricStateModel.kind == observation.resource.kind,
                ResourceMetricStateModel.namespace == namespace,
                ResourceMetricStateModel.name == observation.resource.name,
                ResourceMetricStateModel.container_name == container_name,
            )
        )
        if state is None:
            state = ResourceMetricStateModel(
                cluster_id=cluster_id,
                api_version=observation.resource.api_version,
                kind=observation.resource.kind,
                namespace=namespace,
                name=observation.resource.name,
                container_name=container_name,
                sampled_at=observation.observed_at,
            )
            session.add(state)
            cpu_previous = memory_previous = 0
        else:
            cpu_previous = state.consecutive_cpu_over_threshold
            memory_previous = state.consecutive_memory_over_threshold
        facts = dict(observation.facts)
        stale = bool(facts.get("stale"))
        if trigger == InspectionTrigger.scheduled and not stale:
            cpu_percent = facts.get("cpu_limit_percent")
            memory_percent = facts.get("memory_limit_percent")
            state.consecutive_cpu_over_threshold = (
                cpu_previous + 1
                if cpu_percent is not None and float(cpu_percent) >= threshold
                else 0
            )
            state.consecutive_memory_over_threshold = (
                memory_previous + 1
                if memory_percent is not None and float(memory_percent) >= threshold
                else 0
            )
        state.sampled_at = observation.observed_at
        state.cpu_millicores = facts.get("cpu_usage_millicores")
        state.memory_bytes = facts.get("memory_usage_bytes")
        state.cpu_request_millicores = facts.get("cpu_request_millicores")
        state.memory_request_bytes = facts.get("memory_request_bytes")
        state.cpu_limit_millicores = facts.get("cpu_limit_millicores")
        state.memory_limit_bytes = facts.get("memory_limit_bytes")
        state.stale = stale
        state.updated_at = utcnow()
        facts["consecutive_cpu_over_threshold"] = state.consecutive_cpu_over_threshold
        facts["consecutive_memory_over_threshold"] = state.consecutive_memory_over_threshold
        enriched.append(observation.model_copy(update={"facts": facts}))
    session.flush()
    return result.model_copy(update={"observations": enriched})


def _persist_check_results(
    session: Session,
    *,
    run_id: int,
    evaluations: list[CheckEvaluation],
) -> None:
    completed_at = utcnow()
    for item in evaluations:
        coverage = Coverage.model_validate(
            sanitize_public_payload(item.coverage.model_dump(mode="json"))
        )
        session.add(
            InspectionCheckResultModel(
                run_id=run_id,
                check_code=coverage.check_code,
                name=coverage.name,
                status=coverage.status.value,
                reason=coverage.reason,
                checked_objects=coverage.checked_objects,
                duration_ms=coverage.duration_ms,
                issue_count=coverage.issue_count,
                scope=item.scope.model_dump(mode="json"),
                scope_key=item.scope_key,
                completed_at=completed_at,
            )
        )
    session.flush()


def _evaluate_templates(
    session: Session,
    *,
    provider: InspectionProvider,
    scope: InspectionScope,
) -> CheckEvaluation:
    started = utcnow()
    try:
        result = diagnosis_service.run_diagnosis(
            session,
            provider,
            DiagnosisRequest(direction="template_check"),
        )
        template_results = result.get("template_match_results") or []
        failed = [
            item
            for item in template_results
            if str(item.get("summary") or "").startswith("无法判断")
        ]
        matches = result.get("matches") or []
        if failed:
            status = CheckStatus.failed
            reason = f"{len(failed)} 个模板因采集失败无法判断"
        elif not template_results:
            status = CheckStatus.skipped
            reason = "未配置启用的故障模板"
        elif matches:
            status = CheckStatus.abnormal
            reason = f"命中 {len(matches)} 个故障模板"
        else:
            status = CheckStatus.passed
            reason = None
        checked_objects = len(template_results)
    except Exception as exc:
        status = CheckStatus.failed
        reason = f"模板匹配执行失败：{type(exc).__name__}"
        checked_objects = 0
    duration_ms = max(0, int((utcnow() - started).total_seconds() * 1000))
    return CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code="template.matching",
            name="故障模板匹配",
            status=status,
            reason=reason,
            checked_objects=checked_objects,
            duration_ms=duration_ms,
            issue_count=0,
        ),
        issue_candidates=[],
    )


def _aggregate_run_status(statuses: list[CheckStatus]) -> InspectionRunStatus:
    if not statuses:
        return InspectionRunStatus.failed
    if all(item == CheckStatus.failed for item in statuses):
        return InspectionRunStatus.failed
    if any(item in {CheckStatus.failed, CheckStatus.skipped} for item in statuses):
        return InspectionRunStatus.partial
    return InspectionRunStatus.succeeded


def _aggregate_coverage(evaluations: list[CheckEvaluation]) -> list[Coverage]:
    grouped: dict[str, list[Coverage]] = {}
    for item in evaluations:
        grouped.setdefault(item.coverage.check_code, []).append(item.coverage)
    result: list[Coverage] = []
    for check_code in sorted(grouped):
        items = grouped[check_code]
        statuses = {item.status for item in items}
        if CheckStatus.failed in statuses:
            status = CheckStatus.failed
        elif CheckStatus.abnormal in statuses:
            status = CheckStatus.abnormal
        elif CheckStatus.skipped in statuses:
            status = CheckStatus.skipped
        else:
            status = CheckStatus.passed
        reasons = list(dict.fromkeys(item.reason for item in items if item.reason))
        reason = None
        if status != CheckStatus.passed:
            scope_summary = f"{len(items)} 个范围中有检查未通过"
            reason = f"{scope_summary}：{'；'.join(reasons[:3])}" if reasons else scope_summary
        result.append(
            Coverage(
                check_code=check_code,
                name=items[0].name,
                status=status,
                reason=reason,
                checked_objects=sum(item.checked_objects for item in items),
                duration_ms=sum(item.duration_ms for item in items),
                issue_count=sum(item.issue_count for item in items),
            )
        )
    return result


def _update_registry(
    registry: ComponentStatusRegistry | None,
    row: InspectionRunModel,
) -> None:
    if registry is None:
        return
    state = ComponentState.failed if row.status == InspectionRunStatus.failed.value else (
        ComponentState.degraded if row.status == InspectionRunStatus.partial.value else ComponentState.ok
    )
    registry.update(
        "last_inspection",
        SystemComponentStatus(
            state=state,
            message=f"最近巡检状态：{row.status}",
            checked_at=utcnow(),
            details={"run_id": row.id},
        ),
    )
    metrics = next(
        (
            item
            for item in (row.coverage or [])
            if item.get("check_code") == "metrics.resource"
        ),
        None,
    )
    if metrics is not None:
        metrics_status = metrics.get("status")
        registry.update(
            "metrics_api",
            SystemComponentStatus(
                state=(
                    ComponentState.ok
                    if metrics_status in {"passed", "abnormal"}
                    else ComponentState.unavailable
                    if metrics_status == "skipped"
                    else ComponentState.degraded
                ),
                message=(
                    "Metrics API 已完成本轮采样"
                    if metrics_status in {"passed", "abnormal"}
                    else str(metrics.get("reason") or "Metrics API 当前不可用")
                ),
                checked_at=utcnow(),
                details={"checked_objects": int(metrics.get("checked_objects") or 0)},
            ),
        )


def _update_kubernetes_registry(
    registry: ComponentStatusRegistry | None,
    *,
    provider_mode: str,
    collections: list[tuple[InspectionScope, ProviderCollectionResult]],
) -> None:
    if registry is None:
        return
    normalized_mode = provider_mode.strip().casefold()
    if normalized_mode == "mock":
        registry.update_kubernetes_version(None, None)
        registry.update(
            "kubernetes_api",
            SystemComponentStatus(
                state=ComponentState.unavailable,
                message="Mock Provider 不代表真实 Kubernetes 连接",
                checked_at=utcnow(),
                details={"mode": "mock"},
            ),
        )
        return
    if normalized_mode != "kubernetes":
        return

    version_observations = [
        observation
        for _, result in collections
        for observation in result.observations
        if observation.resource.kind == "KubernetesVersion"
    ]
    failed_scope_count = sum(
        any(failure.check_code == "kubernetes.version" for failure in result.failures)
        for _, result in collections
    )
    successful_business_observations = sum(
        observation.resource.kind != "KubernetesVersion"
        for _, result in collections
        for observation in result.observations
    )
    if version_observations:
        version = version_observations[0]
        supported = version.facts.get("supported")
        registry.update_kubernetes_version(
            version.observed_state,
            supported if isinstance(supported, bool) and version.observed_state else None,
        )
        registry.update(
            "kubernetes_api",
            SystemComponentStatus(
                state=ComponentState.ok,
                message="Kubernetes API 可访问",
                checked_at=utcnow(),
                details={
                    "mode": "kubernetes",
                    "successful_version_observations": len(version_observations),
                    "failed_scope_count": failed_scope_count,
                },
            ),
        )
        return
    if failed_scope_count:
        registry.update_kubernetes_version(None, None)
        registry.update(
            "kubernetes_api",
            SystemComponentStatus(
                state=(
                    ComponentState.failed
                    if (
                        failed_scope_count == len(collections)
                        and successful_business_observations == 0
                    )
                    else ComponentState.degraded
                ),
                message="Kubernetes 版本 API 探测失败",
                checked_at=utcnow(),
                details={
                    "mode": "kubernetes",
                    "failed_scope_count": failed_scope_count,
                    "scope_count": len(collections),
                    "successful_business_observations": successful_business_observations,
                },
            ),
        )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

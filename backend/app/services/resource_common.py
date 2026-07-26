"""Shared helpers for v1.1 resource evaluators."""

from __future__ import annotations

from typing import Any

from app.schemas.v1_1 import (
    CheckEvaluation,
    CheckStatus,
    Coverage,
    Evidence,
    EvidenceSource,
    InspectionScope,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderCollectionFailure,
    ProviderCollectionResult,
    ProviderObservation,
    build_inspection_scope_key,
)


CHECK_NAMES = {
    "kubernetes.version": "Kubernetes 版本兼容性",
    "workload.status": "工作负载状态",
    "required_components": "必需组件",
    "pod.runtime": "Pod 运行与配置依赖",
    "service.endpoints": "Service 与 EndpointSlice",
    "ingress.config_chain": "Ingress 配置链路",
    "tls.certificate": "TLS 证书",
    "storage.status": "存储状态",
    "node.health": "Node 健康",
    "metrics.resource": "CPU 与内存指标",
}

WORKLOAD_KINDS = {"deployment", "statefulset", "daemonset", "job", "cronjob"}
METRIC_KINDS = {"podmetric", "nodemetric"}


def kind(observation: ProviderObservation) -> str:
    return observation.resource.kind.casefold()


def items(
    result: ProviderCollectionResult,
    *kinds: str,
) -> list[ProviderObservation]:
    accepted = {item.casefold() for item in kinds}
    return [item for item in result.observations if kind(item) in accepted]


def evidence(
    observation: ProviderObservation,
    *,
    code: str,
    summary: str,
    facts: dict[str, Any] | None = None,
    source: EvidenceSource = EvidenceSource.kubernetes_api,
) -> Evidence:
    return Evidence(
        code=code,
        source=source,
        summary=summary,
        facts=facts or {},
        related_resources=observation.related_resources[:50],
        observed_at=observation.observed_at,
    )


def candidate(
    observation: ProviderObservation,
    *,
    check_code: str,
    issue_code: IssueCode,
    severity: IssueSeverity,
    scope: IssueScope,
    summary: str,
    reason: str,
    suggestion: str,
    evidence_items: list[Evidence],
    correlation_key: str | None = None,
) -> IssueCandidate:
    return IssueCandidate(
        issue_code=issue_code,
        severity=severity,
        scope=scope,
        resource=observation.resource,
        summary=summary,
        reason=reason,
        suggestion=suggestion,
        evidence=evidence_items,
        source_check=check_code,
        correlation_key=correlation_key,
    )


def failures_for(
    result: ProviderCollectionResult,
    check_code: str,
) -> list[ProviderCollectionFailure]:
    return [item for item in result.failures if item.check_code == check_code]


def evaluation(
    *,
    scope: InspectionScope,
    check_code: str,
    checked_objects: int,
    candidates: list[IssueCandidate],
    duration_ms: int,
    failures: list[ProviderCollectionFailure] | None = None,
    skipped_reason: str | None = None,
) -> CheckEvaluation:
    relevant_failures = failures or []
    if relevant_failures:
        status = CheckStatus.failed
        reason = "；".join(item.message for item in relevant_failures)[:2000]
        candidates = []
    elif candidates:
        status = CheckStatus.abnormal
        reason = f"发现 {len(candidates)} 个异常"
    elif skipped_reason:
        status = CheckStatus.skipped
        reason = skipped_reason
    else:
        status = CheckStatus.passed
        reason = None
    return CheckEvaluation(
        scope=scope,
        scope_key=build_inspection_scope_key(scope),
        coverage=Coverage(
            check_code=check_code,
            name=CHECK_NAMES[check_code],
            status=status,
            reason=reason,
            checked_objects=checked_objects,
            duration_ms=duration_ms,
            issue_count=len(candidates),
        ),
        issue_candidates=candidates,
    )


def resource_scope(observation: ProviderObservation) -> IssueScope:
    resource_kind = kind(observation)
    if resource_kind in {"pod", "podmetric"}:
        return IssueScope.pod
    if resource_kind == "service":
        return IssueScope.service
    if resource_kind == "ingress":
        return IssueScope.ingress
    if resource_kind in {"node", "nodemetric"}:
        return IssueScope.node
    if resource_kind in {"persistentvolume", "persistentvolumeclaim"}:
        return IssueScope.storage
    if resource_kind in WORKLOAD_KINDS:
        return IssueScope.workload
    return (
        IssueScope.namespace
        if observation.resource.namespace
        else IssueScope.cluster
    )

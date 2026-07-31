"""Orchestration for independent v1.1 resource evaluators."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.v1_1 import (
    CheckEvaluation,
    InspectionPolicySettings,
    InspectionScope,
    InspectionTrigger,
    ProviderCollectionResult,
)
from app.services.resource_common import (
    METRIC_KINDS,
    REQUIRED_COMPONENT_KINDS,
    WORKLOAD_KINDS,
    evaluation,
    failures_for,
    items,
    kind,
)
from app.services.resource_network import (
    ingress_candidates,
    service_candidates,
    tls_candidates,
)
from app.services.resource_nodes import metrics_candidates, node_candidates
from app.services.resource_pods import pod_candidates
from app.services.resource_storage import storage_candidates
from app.services.resource_workloads import (
    required_component_candidates,
    workload_candidates,
)

REQUIRED_COMPONENT_COLLECTION_CHECKS = {
    "deployment": "workload.status",
    "statefulset": "workload.status",
    "daemonset": "workload.status",
    "job": "workload.status",
    "cronjob": "workload.status",
    "pod": "pod.runtime",
    "service": "service.endpoints",
}


def _required_component_failures(result: ProviderCollectionResult, policy: InspectionPolicySettings):
    required_namespaces = {item.namespace for item in policy.required_components if item.enabled}
    required_checks = {
        REQUIRED_COMPONENT_COLLECTION_CHECKS.get(item.kind.casefold())
        for item in policy.required_components
        if item.enabled
    }
    required_checks.discard(None)
    failures = failures_for(result, "required_components")
    failures.extend(
        failure
        for failure in result.failures
        if failure.check_code in required_checks
        and failure.resource
        and (
            failure.resource.namespace in required_namespaces
            or (
                failure.resource.kind.casefold() == "namespace"
                and failure.resource.name in required_namespaces
            )
        )
    )
    return failures


def evaluate_resource_collection(
    result: ProviderCollectionResult,
    *,
    scope: InspectionScope,
    policy: InspectionPolicySettings,
    trigger: InspectionTrigger,
    now: datetime | None = None,
) -> list[CheckEvaluation]:
    """Evaluate one collection using its exact scope and frozen DTOs."""

    observed_at = now or datetime.now(timezone.utc)
    if scope.type.value == "cluster":
        namespace_names = {
            item.resource.namespace
            for item in result.observations
            if item.resource.namespace
        }
        namespace_names.update(
            failure.resource.name
            for failure in result.failures
            if failure.resource
            and failure.resource.kind.casefold() == "namespace"
        )
        namespace_names.update(
            failure.resource.namespace
            for failure in result.failures
            if failure.resource and failure.resource.namespace
        )
        if namespace_names:
            namespace_codes = {
                "workload.status",
                "pod.runtime",
                "service.endpoints",
                "ingress.config_chain",
                "tls.certificate",
                "storage.status",
                "metrics.resource",
            }
            shared_failure_codes = {
                "ingress.config_chain",
                "storage.status",
                "metrics.resource",
            }
            scoped_evaluations: list[CheckEvaluation] = []
            for namespace in sorted(namespace_names):
                namespace_result = ProviderCollectionResult(
                    layer=result.layer,
                    observations=[
                        item
                        for item in result.observations
                        if item.resource.namespace == namespace
                    ],
                    failures=[
                        failure
                        for failure in result.failures
                        if (
                            failure.resource
                            and (
                                failure.resource.namespace == namespace
                                or (
                                    failure.resource.kind.casefold()
                                    == "namespace"
                                    and failure.resource.name == namespace
                                )
                            )
                        )
                        or (
                            failure.resource is None
                            and failure.check_code in shared_failure_codes
                        )
                    ],
                    duration_ms=result.duration_ms,
                )
                namespace_scope = InspectionScope(
                    type="namespace",
                    namespace=namespace,
                )
                scoped_evaluations.extend(
                    item
                    for item in evaluate_resource_collection(
                        namespace_result,
                        scope=namespace_scope,
                        policy=InspectionPolicySettings(
                            required_components=[],
                            thresholds=policy.thresholds,
                        ),
                        trigger=trigger,
                        now=observed_at,
                    )
                    if item.coverage.check_code in namespace_codes
                )

            global_result = ProviderCollectionResult(
                layer=result.layer,
                observations=[
                    item
                    for item in result.observations
                    if item.resource.namespace is None
                ],
                failures=[
                    failure
                    for failure in result.failures
                    if failure.resource is None
                    or (
                        failure.resource.namespace is None
                        and failure.resource.kind.casefold() != "namespace"
                    )
                ],
                duration_ms=result.duration_ms,
            )
            global_evaluations = evaluate_resource_collection(
                global_result,
                scope=scope,
                policy=InspectionPolicySettings(
                    required_components=[],
                    thresholds=policy.thresholds,
                ),
                trigger=trigger,
                now=observed_at,
            )
            required_issues = required_component_candidates(
                [
                    item
                    for item in result.observations
                    if kind(item) in REQUIRED_COMPONENT_KINDS
                ],
                policy,
                observed_at,
            )
            required_evaluation = evaluation(
                scope=scope,
                check_code="required_components",
                checked_objects=len(policy.required_components),
                candidates=required_issues,
                duration_ms=result.duration_ms,
                failures=_required_component_failures(result, policy),
                skipped_reason=(
                    None
                    if any(
                        item.enabled
                        for item in policy.required_components
                    )
                    else "未配置必需组件策略；可选组件缺失不告警"
                ),
            )
            global_evaluations = [
                required_evaluation
                if item.coverage.check_code == "required_components"
                else item
                for item in global_evaluations
            ]
            return [*global_evaluations, *scoped_evaluations]

    duration = result.duration_ms
    evaluations: list[CheckEvaluation] = []

    version_items = items(result, "KubernetesVersion")
    unsupported = [
        item for item in version_items if item.facts.get("supported") is False
    ]
    version_skip = (
        f"Kubernetes {unsupported[0].observed_state} 不在商用支持范围 1.34-1.36"
        if unsupported
        else "未读取 Kubernetes 服务端版本"
        if not version_items
        else None
    )
    evaluations.append(
        evaluation(
            scope=scope,
            check_code="kubernetes.version",
            checked_objects=len(version_items),
            candidates=[],
            duration_ms=duration,
            failures=failures_for(result, "kubernetes.version"),
            skipped_reason=version_skip,
        )
    )

    workload_items = [
        item for item in result.observations if kind(item) in WORKLOAD_KINDS
    ]
    required_component_items = [
        item for item in result.observations if kind(item) in REQUIRED_COMPONENT_KINDS
    ]
    required_issues = (
        required_component_candidates(
            required_component_items,
            policy,
            observed_at,
        )
        if scope.type.value == "cluster"
        else []
    )
    evaluations.append(
        evaluation(
            scope=scope,
            check_code="required_components",
            checked_objects=len(policy.required_components),
            candidates=required_issues,
            duration_ms=duration,
            failures=_required_component_failures(result, policy),
            skipped_reason=(
                "必需组件是集群级策略，仅在全集群巡检中检查"
                if scope.type.value != "cluster"
                else
                None
                if any(item.enabled for item in policy.required_components)
                else "未配置必需组件策略；可选组件缺失不告警"
            ),
        )
    )

    domain_specs = (
        (
            "workload.status",
            workload_items,
            workload_candidates(workload_items, policy),
        ),
        (
            "pod.runtime",
            items(result, "Pod"),
            pod_candidates(items(result, "Pod"), policy),
        ),
        (
            "service.endpoints",
            items(result, "Service"),
            service_candidates(items(result, "Service")),
        ),
        (
            "ingress.config_chain",
            items(result, "Ingress"),
            ingress_candidates(items(result, "Ingress")),
        ),
        (
            "storage.status",
            items(result, "PersistentVolumeClaim", "PersistentVolume"),
            storage_candidates(
                items(result, "PersistentVolumeClaim", "PersistentVolume"),
                policy,
            ),
        ),
        (
            "node.health",
            items(result, "Node"),
            node_candidates(items(result, "Node"), policy),
        ),
    )
    for check_code, observations, issues in domain_specs:
        evaluations.append(
            evaluation(
                scope=scope,
                check_code=check_code,
                checked_objects=len(observations),
                candidates=issues,
                duration_ms=duration,
                failures=failures_for(result, check_code),
                skipped_reason=None,
            )
        )

    tls_items = items(result, "TLSSecret")
    evaluations.append(
        evaluation(
            scope=scope,
            check_code="tls.certificate",
            checked_objects=len(tls_items),
            candidates=tls_candidates(tls_items, policy),
            duration_ms=duration,
            failures=failures_for(result, "tls.certificate"),
            skipped_reason=None,
        )
    )

    metric_items = [
        item for item in result.observations if kind(item) in METRIC_KINDS
    ]
    available_metrics = [
        item
        for item in metric_items
        if bool(item.facts.get("metrics_available"))
        and not bool(item.facts.get("stale"))
    ]
    evaluations.append(
        evaluation(
            scope=scope,
            check_code="metrics.resource",
            checked_objects=len(available_metrics),
            candidates=metrics_candidates(
                available_metrics,
                policy,
                trigger,
            ),
            duration_ms=duration,
            failures=failures_for(result, "metrics.resource"),
            skipped_reason=(
                None
                if available_metrics
                else "Metrics API 不可用、无当前样本或样本已陈旧"
            ),
        )
    )
    return evaluations

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
                    if kind(item) in WORKLOAD_KINDS
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
                failures=failures_for(result, "required_components"),
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
    required_issues = required_component_candidates(
        workload_items,
        policy,
        observed_at,
    )
    evaluations.append(
        evaluation(
            scope=scope,
            check_code="required_components",
            checked_objects=len(policy.required_components),
            candidates=required_issues,
            duration_ms=duration,
            failures=failures_for(result, "required_components"),
            skipped_reason=(
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
            "当前范围没有工作负载对象",
        ),
        (
            "pod.runtime",
            items(result, "Pod"),
            pod_candidates(items(result, "Pod"), policy),
            "当前范围没有 Pod",
        ),
        (
            "service.endpoints",
            items(result, "Service"),
            service_candidates(items(result, "Service")),
            "当前范围没有 Service",
        ),
        (
            "ingress.config_chain",
            items(result, "Ingress"),
            ingress_candidates(items(result, "Ingress")),
            "当前范围没有 Ingress",
        ),
        (
            "storage.status",
            items(result, "PersistentVolumeClaim", "PersistentVolume"),
            storage_candidates(
                items(result, "PersistentVolumeClaim", "PersistentVolume"),
                policy,
            ),
            "当前范围没有 PVC 或 PV",
        ),
        (
            "node.health",
            items(result, "Node"),
            node_candidates(items(result, "Node"), policy),
            "当前范围没有 Node",
        ),
    )
    for check_code, observations, issues, empty_reason in domain_specs:
        skipped_reason = empty_reason if not observations else None
        if check_code == "service.endpoints" and observations:
            applicable = [
                item
                for item in observations
                if str(item.facts.get("service_type") or "").casefold()
                != "externalname"
                and not (
                    not bool(item.facts.get("selector_present"))
                    and int(item.facts.get("endpoint_slices") or 0) == 0
                    and not bool(item.facts.get("ingress_referenced"))
                )
            ]
            if not applicable:
                skipped_reason = (
                    "范围内仅有 ExternalName，或未被 Ingress 引用且"
                    "没有手工 EndpointSlice 的无 selector Service"
                )
        if check_code == "ingress.config_chain" and observations:
            service_backends = sum(
                int(item.facts.get("service_backends") or 0)
                for item in observations
            )
            resource_backends = sum(
                int(item.facts.get("resource_backends") or 0)
                for item in observations
            )
            if service_backends == 0 and resource_backends > 0:
                skipped_reason = (
                    "Ingress 仅使用 Resource Backend；"
                    "当前版本不判断非 Service 配置链路"
                )
        evaluations.append(
            evaluation(
                scope=scope,
                check_code=check_code,
                checked_objects=len(observations),
                candidates=issues,
                duration_ms=duration,
                failures=failures_for(result, check_code),
                skipped_reason=skipped_reason,
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
            skipped_reason=(
                "当前范围没有 Ingress TLS 引用" if not tls_items else None
            ),
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

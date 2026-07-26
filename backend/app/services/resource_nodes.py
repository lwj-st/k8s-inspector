"""Node condition and optional Metrics API evaluations."""

from app.schemas.v1_1 import (
    EvidenceSource,
    InspectionPolicySettings,
    InspectionTrigger,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderObservation,
)
from app.services.resource_common import (
    candidate,
    evidence,
    resource_scope,
)


def node_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
) -> list[IssueCandidate]:
    check = "node.health"
    issues: list[IssueCandidate] = []
    mappings = (
        ("memory_pressure", IssueCode.NODE_MEMORY_PRESSURE, "MemoryPressure"),
        ("disk_pressure", IssueCode.NODE_DISK_PRESSURE, "DiskPressure"),
        ("pid_pressure", IssueCode.NODE_PID_PRESSURE, "PIDPressure"),
        (
            "network_unavailable",
            IssueCode.NODE_NETWORK_UNAVAILABLE,
            "NetworkUnavailable",
        ),
    )
    for item in items:
        facts = item.facts
        ready = str(facts.get("ready_status") or "Unknown")
        if (
            ready != "True"
            and float(facts.get("ready_age_seconds") or 0)
            >= policy.thresholds.node_not_ready_grace_seconds
        ):
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.NODE_NOT_READY,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.node,
                    summary=f"Node {item.resource.name} 未就绪",
                    reason=f"Ready Condition={ready}。",
                    suggestion="检查节点网络、可见事件和受影响 Pod。",
                    evidence_items=[
                        evidence(
                            item,
                            code="node_ready",
                            summary=f"Ready={ready}",
                            facts={"ready_status": ready},
                        )
                    ],
                )
            )
        for key, code, label in mappings:
            if bool(facts.get(key)):
                severity = (
                    IssueSeverity.critical
                    if bool(facts.get("business_impact"))
                    else IssueSeverity.warning
                )
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=code,
                        severity=severity,
                        scope=IssueScope.node,
                        summary=f"Node {item.resource.name} 出现 {label}",
                        reason=f"{label} Condition=True。",
                        suggestion="检查节点容量、驱逐/调度事件和受影响 Pod。",
                        evidence_items=[
                            evidence(
                                item,
                                code=f"node_{key}",
                                summary=f"{label}=True",
                                facts={key: True},
                            )
                        ],
                    )
                )
    return issues


def metrics_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
    trigger: InspectionTrigger,
) -> list[IssueCandidate]:
    if trigger != InspectionTrigger.scheduled:
        return []
    check = "metrics.resource"
    issues: list[IssueCandidate] = []
    thresholds = policy.thresholds
    for item in items:
        facts = item.facts
        if bool(facts.get("stale")):
            continue
        fallback = int(facts.get("consecutive_over_threshold") or 0)
        cpu_consecutive = int(
            facts.get("consecutive_cpu_over_threshold") or fallback
        )
        memory_consecutive = int(
            facts.get("consecutive_memory_over_threshold") or fallback
        )
        cpu_percent = facts.get("cpu_limit_percent")
        memory_percent = facts.get("memory_limit_percent")
        cpu_over = (
            cpu_percent is not None
            and float(cpu_percent)
            >= thresholds.resource_usage_warning_percent
            and cpu_consecutive
            >= thresholds.resource_usage_consecutive_cycles
        )
        memory_over = (
            memory_percent is not None
            and float(memory_percent)
            >= thresholds.resource_usage_warning_percent
            and memory_consecutive
            >= thresholds.resource_usage_consecutive_cycles
        )
        if cpu_over or memory_over:
            consecutive = max(cpu_consecutive, memory_consecutive)
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.RESOURCE_USAGE_HIGH,
                    severity=IssueSeverity.warning,
                    scope=resource_scope(item),
                    summary=f"{item.resource.kind} {item.resource.name} 资源使用率持续偏高",
                    reason=f"相对 limit 的使用率连续 {consecutive} 个定时周期超过阈值。",
                    suggestion="检查应用负载、requests/limits 和扩缩容策略。",
                    evidence_items=[
                        evidence(
                            item,
                            code="resource_usage_high",
                            summary="资源使用率持续超过 limit 阈值",
                            facts={
                                "cpu_limit_percent": facts.get(
                                    "cpu_limit_percent"
                                ),
                                "memory_limit_percent": facts.get(
                                    "memory_limit_percent"
                                ),
                                "consecutive_cpu_over_threshold": (
                                    cpu_consecutive
                                ),
                                "consecutive_memory_over_threshold": (
                                    memory_consecutive
                                ),
                            },
                            source=EvidenceSource.metrics_api,
                        )
                    ],
                )
            )
    return issues

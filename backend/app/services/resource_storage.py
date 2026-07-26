"""PVC and PV evaluations."""

from app.schemas.v1_1 import (
    InspectionPolicySettings,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderObservation,
)
from app.services.resource_common import candidate, evidence, kind


def storage_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
) -> list[IssueCandidate]:
    check = "storage.status"
    issues: list[IssueCandidate] = []
    thresholds = policy.thresholds
    for item in items:
        facts = item.facts
        phase = str(facts.get("phase") or item.observed_state or "Unknown")
        if kind(item) == "persistentvolumeclaim":
            if (
                phase == "Pending"
                and facts.get("volume_binding_mode") == "WaitForFirstConsumer"
                and int(facts.get("consumer_pods") or 0) == 0
            ):
                continue
            pending = float(facts.get("pending_minutes") or 0)
            if phase in {"Pending", "Lost"} and (
                phase == "Lost"
                or pending >= thresholds.pvc_pending_warning_minutes
            ):
                severity = (
                    IssueSeverity.critical
                    if phase == "Lost"
                    or pending >= thresholds.pvc_pending_critical_minutes
                    or bool(facts.get("blocks_pod"))
                    else IssueSeverity.warning
                )
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.PVC_NOT_BOUND,
                        severity=severity,
                        scope=IssueScope.storage,
                        summary=f"PVC {item.resource.name} 未完成绑定",
                        reason=f"PVC phase={phase}，持续约 {pending:.0f} 分钟。",
                        suggestion="检查 StorageClass、PV、CSI 和 Warning Event。",
                        evidence_items=[
                            evidence(
                                item,
                                code="pvc_not_bound",
                                summary=f"phase={phase}",
                                facts={
                                    "phase": phase,
                                    "pending_minutes": pending,
                                },
                            )
                        ],
                        correlation_key=(
                            f"pvc:{item.resource.namespace or ''}/"
                            f"{item.resource.name}"
                        ),
                    )
                )
        elif kind(item) == "persistentvolume":
            if phase == "Failed":
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.PV_FAILED,
                        severity=IssueSeverity.critical,
                        scope=IssueScope.storage,
                        summary=f"PV {item.resource.name} 状态为 Failed",
                        reason="PersistentVolume 明确报告 Failed。",
                        suggestion="检查存储后端、CSI 和 PV 事件。",
                        evidence_items=[
                            evidence(
                                item,
                                code="pv_failed",
                                summary="PV phase=Failed",
                                facts={"phase": phase},
                            )
                        ],
                    )
                )
            elif (
                phase == "Released"
                and float(facts.get("released_hours") or 0)
                >= thresholds.pv_released_stale_hours
            ):
                released = float(facts.get("released_hours") or 0)
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.PV_RELEASED_STALE,
                        severity=IssueSeverity.info,
                        scope=IssueScope.storage,
                        summary=f"PV {item.resource.name} 等待人工回收",
                        reason=(
                            f"PV 已 Released 约 {released:.0f} 小时；"
                            "Retain 策略下这是清理风险提示，不代表存储故障。"
                        ),
                        suggestion="确认数据保留要求后按流程清理或重新绑定。",
                        evidence_items=[
                            evidence(
                                item,
                                code="pv_released",
                                summary="PV Released 等待回收",
                                facts={
                                    "released_hours": released,
                                    "reclaim_policy": str(
                                        facts.get("reclaim_policy") or ""
                                    ),
                                },
                            )
                        ],
                    )
                )
    return issues

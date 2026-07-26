"""Pod runtime and referenced-object evaluations."""

from app.schemas.v1_1 import (
    EvidenceSource,
    InspectionPolicySettings,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderObservation,
)
from app.services.resource_common import candidate, evidence


def pod_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
) -> list[IssueCandidate]:
    check = "pod.runtime"
    issues: list[IssueCandidate] = []
    for item in items:
        facts = item.facts
        phase = str(facts.get("phase") or item.observed_state or "Unknown")
        if phase.casefold() in {"succeeded", "completed"}:
            continue
        correlation = f"pod:{item.resource.namespace or ''}/{item.resource.name}"
        specs = [
            (
                facts.get("ready") is False,
                IssueCode.POD_NOT_READY,
                f"Pod {item.resource.name} 未就绪",
                (
                    f"Pod phase={phase}，Ready Condition 不是 True。"
                    + (
                        f" 状态原因：{facts.get('status_reason')}。"
                        if facts.get("status_reason")
                        else ""
                    )
                ),
                "检查容器状态、探针、调度和最近 Warning Event。",
                "pod_ready",
                f"phase={phase}, Ready=False",
                {
                    "phase": phase,
                    "ready": False,
                    "status_reason": str(
                        facts.get("status_reason") or ""
                    ),
                    "terminated_reasons": list(
                        facts.get("terminated_reasons") or []
                    )[:50],
                    "last_terminated_reasons": list(
                        facts.get("last_terminated_reasons") or []
                    )[:50],
                },
                EvidenceSource.kubernetes_api,
            ),
            (
                bool(facts.get("init_failure_reason")),
                IssueCode.POD_INIT_CONTAINER_FAILED,
                f"Pod {item.resource.name} 的 init container 失败",
                f"init container 状态：{facts.get('init_failure_reason')}。",
                "检查 init container 的退出码、依赖和受限日志上下文。",
                "pod_init_failed",
                f"init reason={facts.get('init_failure_reason')}",
                {"reason": str(facts.get("init_failure_reason"))},
                EvidenceSource.kubernetes_api,
            ),
            (
                bool(facts.get("image_pull_reason")),
                IssueCode.POD_IMAGE_PULL_FAILED,
                f"Pod {item.resource.name} 镜像拉取失败",
                f"容器等待原因：{facts.get('image_pull_reason')}。",
                "检查镜像地址、仓库凭证和节点到仓库的访问条件。",
                "pod_image_pull",
                str(facts.get("image_pull_reason")),
                {"reason": str(facts.get("image_pull_reason"))},
                EvidenceSource.kubernetes_api,
            ),
            (
                bool(facts.get("probe_failure")),
                IssueCode.POD_PROBE_FAILED,
                f"Pod {item.resource.name} 探针失败",
                "近期 Warning Event 包含明确的探针失败。",
                "检查探针路径、端口、超时和应用启动耗时。",
                "pod_probe_failed",
                "近期探针失败",
                {"probe_failure": True},
                EvidenceSource.event,
            ),
        ]
        for (
            matched,
            code,
            summary,
            reason,
            suggestion,
            evidence_code,
            evidence_summary,
            evidence_facts,
            source,
        ) in specs:
            if matched:
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=code,
                        severity=IssueSeverity.warning,
                        scope=IssueScope.pod,
                        summary=summary,
                        reason=reason,
                        suggestion=suggestion,
                        evidence_items=[
                            evidence(
                                item,
                                code=evidence_code,
                                summary=evidence_summary,
                                facts=evidence_facts,
                                source=source,
                            )
                        ],
                        correlation_key=correlation,
                    )
                )
        missing = [str(value) for value in facts.get("missing_references", [])]
        if missing:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.POD_CONFIG_REFERENCE_MISSING,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.pod,
                    summary=f"Pod {item.resource.name} 引用的配置对象不存在",
                    reason="缺失引用：" + "、".join(missing[:20]),
                    suggestion="修正 Pod 模板中的对象名称或补齐引用对象。",
                    evidence_items=[
                        evidence(
                            item,
                            code="pod_reference_missing",
                            summary="发现缺失引用对象",
                            facts={"missing_references": missing[:50]},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        deletion_age = float(facts.get("deletion_age_minutes") or 0)
        if (
            deletion_age
            >= policy.thresholds.pod_terminating_warning_minutes
        ):
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.POD_TERMINATING_STUCK,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.pod,
                    summary=f"Pod {item.resource.name} 长时间处于 Terminating",
                    reason=f"删除时间已持续约 {deletion_age:.0f} 分钟。",
                    suggestion="检查 finalizer、卷卸载、节点状态和终止宽限期。",
                    evidence_items=[
                        evidence(
                            item,
                            code="pod_terminating",
                            summary="Pod 删除超时",
                            facts={"deletion_age_minutes": deletion_age},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        restart_delta = int(facts.get("restart_delta") or 0)
        if restart_delta >= policy.thresholds.pod_restart_delta:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.POD_RESTART_SPIKE,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.pod,
                    summary=f"Pod {item.resource.name} 在时间窗口内重启突增",
                    reason=f"窗口内重启次数增加 {restart_delta} 次。",
                    suggestion="检查 last terminated reason、退出码和 Warning Event。",
                    evidence_items=[
                        evidence(
                            item,
                            code="pod_restart_delta",
                            summary=f"restart delta={restart_delta}",
                            facts={"restart_delta": restart_delta},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        warning_reasons = [
            str(value) for value in facts.get("warning_reasons", [])
        ]
        if warning_reasons:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.POD_WARNING_EVENT,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.pod,
                    summary=f"Pod {item.resource.name} 存在近期 Warning Event",
                    reason="、".join(warning_reasons[:20]),
                    suggestion="结合 Event 时间、次数和当前容器状态确认影响。",
                    evidence_items=[
                        evidence(
                            item,
                            code="pod_warning_event",
                            summary="近期 Warning Event",
                            facts={"reasons": warning_reasons[:50]},
                            source=EvidenceSource.event,
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        if bool(facts.get("volume_mount_failure")):
            related_pvc = next(
                (
                    resource
                    for resource in item.related_resources
                    if resource.kind.casefold()
                    == "persistentvolumeclaim"
                ),
                None,
            )
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.VOLUME_MOUNT_FAILED,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.pod,
                    summary=f"Pod {item.resource.name} 卷挂载失败",
                    reason="近期 Warning Event 包含 Attach、Mount 或卷绑定失败。",
                    suggestion="检查关联 PVC、PV、StorageClass 和 CSI 组件。",
                    evidence_items=[
                        evidence(
                            item,
                            code="pod_volume_mount",
                            summary="卷挂载或绑定失败",
                            facts={"volume_mount_failure": True},
                            source=EvidenceSource.event,
                        )
                    ],
                    correlation_key=(
                        f"pvc:{related_pvc.namespace or ''}/"
                        f"{related_pvc.name}"
                        if related_pvc
                        else correlation
                    ),
                )
            )
    return issues

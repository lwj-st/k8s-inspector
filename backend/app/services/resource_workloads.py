"""Workload and required-component evaluations."""

from __future__ import annotations

import re
from datetime import datetime

from app.schemas.v1_1 import (
    EvidenceSource,
    InspectionPolicySettings,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderObservation,
    ResourceRef,
)
from app.services.resource_common import candidate, evidence, kind


def workload_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
) -> list[IssueCandidate]:
    check = "workload.status"
    issues: list[IssueCandidate] = []
    for item in items:
        facts = item.facts
        resource_kind = kind(item)
        if resource_kind in {"deployment", "statefulset"}:
            desired = int(facts.get("desired") or 0)
            ready = int(facts.get("ready") or 0)
            if desired == 0 or bool(facts.get("paused")):
                continue
            if bool(facts.get("progress_deadline_exceeded")):
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.WORKLOAD_ROLLOUT_STALLED,
                        severity=IssueSeverity.critical,
                        scope=IssueScope.workload,
                        summary=f"{item.resource.kind} {item.resource.name} 发布停滞",
                        reason="控制器报告 ProgressDeadlineExceeded。",
                        suggestion="检查镜像、探针、调度事件和关联 Pod。",
                        evidence_items=[
                            evidence(
                                item,
                                code="workload_progress_deadline",
                                summary="控制器发布超过进度期限",
                                facts={"desired": desired, "ready": ready},
                            )
                        ],
                    )
                )
            elif ready < desired:
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.WORKLOAD_REPLICAS_UNAVAILABLE,
                        severity=IssueSeverity.warning,
                        scope=IssueScope.workload,
                        summary=f"{item.resource.kind} {item.resource.name} 可用副本不足",
                        reason=f"期望 {desired} 个副本，当前 Ready {ready} 个。",
                        suggestion="检查关联 Pod 的 Ready、调度、镜像和挂载状态。",
                        evidence_items=[
                            evidence(
                                item,
                                code="workload_replicas",
                                summary=f"desired={desired}, ready={ready}",
                                facts={
                                    "desired": desired,
                                    "ready": ready,
                                    "available": int(facts.get("available") or 0),
                                    "updated": int(facts.get("updated") or 0),
                                },
                            )
                        ],
                    )
                )
        elif resource_kind == "daemonset":
            desired = int(facts.get("desired") or 0)
            unavailable = int(facts.get("unavailable") or 0)
            if desired > 0 and unavailable > 0:
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.WORKLOAD_REPLICAS_UNAVAILABLE,
                        severity=IssueSeverity.warning,
                        scope=IssueScope.workload,
                        summary=f"DaemonSet {item.resource.name} 存在不可用实例",
                        reason=f"期望调度 {desired} 个，当前不可用 {unavailable} 个。",
                        suggestion="检查未调度节点、污点容忍和关联 Pod。",
                        evidence_items=[
                            evidence(
                                item,
                                code="daemonset_unavailable",
                                summary=f"desired={desired}, unavailable={unavailable}",
                                facts={"desired": desired, "unavailable": unavailable},
                            )
                        ],
                    )
                )
        elif resource_kind == "job":
            failed = int(facts.get("failed") or 0)
            failed_condition = bool(facts.get("failure_condition"))
            deadline_exceeded = bool(facts.get("deadline_exceeded"))
            if failed > 0 or failed_condition or deadline_exceeded:
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.JOB_FAILED,
                        severity=IssueSeverity.warning,
                        scope=IssueScope.workload,
                        summary=f"Job {item.resource.name} 执行失败",
                        reason="Job 存在失败实例、失败 Condition 或超过自身 deadline。",
                        suggestion="检查 Job Condition、Pod 退出原因和 Warning Event。",
                        evidence_items=[
                            evidence(
                                item,
                                code="job_failed",
                                summary="Job 失败状态明确",
                                facts={
                                    "failed": failed,
                                    "failure_condition": failed_condition,
                                    "deadline_exceeded": deadline_exceeded,
                                },
                            )
                        ],
                    )
                )
            elif (
                not bool(facts.get("completion_condition"))
                and not facts.get("active_deadline_seconds")
                and float(facts.get("age_minutes") or 0)
                >= policy.thresholds.job_incomplete_info_minutes
            ):
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.JOB_FAILED,
                        severity=IssueSeverity.info,
                        scope=IssueScope.workload,
                        summary=f"Job {item.resource.name} 长时间未完成",
                        reason="Job 未配置 activeDeadlineSeconds，当前仅提示执行时长风险，不判定失败。",
                        suggestion="确认预期执行时长，必要时配置 deadline 或模板规则。",
                        evidence_items=[
                            evidence(
                                item,
                                code="job_long_running",
                                summary="Job 未配置 deadline 且运行时间较长",
                                facts={
                                    "age_minutes": float(
                                        facts.get("age_minutes") or 0
                                    )
                                },
                            )
                        ],
                    )
                )
        elif resource_kind == "cronjob" and not bool(facts.get("suspended")):
            failed_jobs = int(facts.get("failed_jobs") or 0)
            missed_schedule = bool(facts.get("missed_schedule"))
            if failed_jobs > 0 or missed_schedule:
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=IssueCode.CRONJOB_NOT_SCHEDULED,
                        severity=IssueSeverity.warning,
                        scope=IssueScope.workload,
                        summary=f"CronJob {item.resource.name} 调度或执行异常",
                        reason="发现连续失败 Job 或明确漏调度。",
                        suggestion="检查时区、调度表达式、startingDeadlineSeconds 和关联 Job。",
                        evidence_items=[
                            evidence(
                                item,
                                code="cronjob_schedule",
                                summary="CronJob 存在调度异常证据",
                                facts={
                                    "failed_jobs": failed_jobs,
                                    "missed_schedule": missed_schedule,
                                },
                            )
                        ],
                    )
                )
    return issues


def _selector_requirements(selector: str) -> list[str]:
    requirements: list[str] = []
    start = depth = 0
    for index, char in enumerate(selector):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            requirements.append(selector[start:index].strip())
            start = index + 1
    requirements.append(selector[start:].strip())
    return [item for item in requirements if item]


def _selector_matches(selector: str, labels: set[str]) -> bool:
    values = {
        key: value
        for key, separator, value in (
            item.partition("=") for item in labels
        )
        if separator
    }
    requirements = _selector_requirements(selector)
    if not requirements:
        return False
    for requirement in requirements:
        set_match = re.fullmatch(
            r"([A-Za-z0-9_.\-/]+)\s+(in|notin)\s+\(([^)]*)\)",
            requirement,
        )
        if set_match:
            key, operator, raw = set_match.groups()
            expected = {
                item.strip() for item in raw.split(",") if item.strip()
            }
            present = values.get(key) in expected
            if (operator == "in" and not present) or (
                operator == "notin" and present
            ):
                return False
            continue
        if requirement.startswith("!"):
            if requirement[1:].strip() in values:
                return False
            continue
        if "!=" in requirement:
            key, expected = [
                item.strip() for item in requirement.split("!=", 1)
            ]
            if values.get(key) == expected:
                return False
            continue
        separator = "==" if "==" in requirement else "="
        if separator in requirement:
            key, expected = [
                item.strip() for item in requirement.split(separator, 1)
            ]
            if values.get(key) != expected:
                return False
            continue
        if requirement not in values:
            return False
    return True


def required_component_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
    observed_at: datetime,
) -> list[IssueCandidate]:
    check = "required_components"
    issues: list[IssueCandidate] = []
    for required in policy.required_components:
        if not required.enabled:
            continue
        found = any(
            item.resource.namespace == required.namespace
            and item.resource.kind.casefold() == required.kind.casefold()
            and _selector_matches(
                required.label_selector,
                {str(value) for value in item.facts.get("labels", [])},
            )
            for item in items
        )
        if found:
            continue
        synthetic = ProviderObservation(
            resource=ResourceRef(
                kind=required.kind,
                namespace=required.namespace,
                name=required.name,
            ),
            observed_at=observed_at,
            observed_state="missing",
            facts={
                "required_component": required.name,
                "label_selector": required.label_selector,
            },
        )
        issues.append(
            candidate(
                synthetic,
                check_code=check,
                issue_code=IssueCode.REQUIRED_COMPONENT_MISSING,
                severity=IssueSeverity.critical,
                scope=IssueScope.workload,
                summary=f"必需组件 {required.name} 不存在",
                reason=(
                    f"未找到 namespace={required.namespace}、"
                    f"kind={required.kind}、selector={required.label_selector} 的对象。"
                ),
                suggestion="确认组件是否安装，或修正必需组件定位策略。",
                evidence_items=[
                    evidence(
                        synthetic,
                        code="required_component_missing",
                        summary="未发现契约配置的必需组件",
                        facts={
                            "namespace": required.namespace,
                            "kind": required.kind,
                            "label_selector": required.label_selector,
                        },
                        source=EvidenceSource.derived,
                    )
                ],
            )
        )
    return issues

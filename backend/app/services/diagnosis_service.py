import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatchcase

from sqlalchemy.orm import Session

from app.engine.matcher import describe_condition, match_template
from app.models import DiagnosisRecord, FaultTemplate, SystemSetting
from app.providers.base import InspectionProvider, LogPodLimitExceededError
from app.schemas.diagnosis import DiagnosisRequest
from app.schemas.v1_1 import CollectionLimits, InspectionPolicySettings
from app.services import keyword_service
from app.services.payload_sanitizer import (
    sanitize_persistence_payload,
    sanitize_public_payload,
)
from app.services.settings_service import policy_with_builtin_required_components


@dataclass
class _DiagnosisLogBudget:
    limits: CollectionLimits
    collected_bytes: int = 0
    targeted_pods: set[tuple[str, str]] = field(default_factory=set)
    samples_by_namespace: dict[str, dict[str, dict[str, str]]] = field(
        default_factory=dict
    )


def _normalize_condition_result(condition: dict, matched: bool, evidence: list[dict]) -> dict:
    return {
        "target_ref": condition.get("target_ref"),
        "type": condition.get("type") or condition.get("condition_type"),
        "operator": condition.get("operator"),
        "value": condition.get("value", condition.get("expected_value")),
        "matched": matched,
        "evidence": evidence,
    }


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _template_log_keywords_by_target(template: FaultTemplate) -> dict[str, list[str]]:
    keywords_by_target: dict[str, list[str]] = {}
    for condition in template.match_conditions:
        condition_type = condition.get("condition_type") or condition.get("type")
        if condition_type != "log_keyword" or not condition.get("enabled", True):
            continue
        target_ref = condition.get("target_ref", "default")
        values = [str(item) for item in _as_list(condition.get("expected_value", condition.get("value"))) if item]
        keywords_by_target.setdefault(target_ref, []).extend(values)
    return keywords_by_target


def _attach_log_hits(
    session: Session,
    namespace: str,
    label_selector: str | None,
    pod: dict,
    template_keywords: list[str] | None = None,
) -> dict:
    pod_copy = dict(pod)
    hits = []
    container_logs = pod.get("container_log_summaries") or {}
    if container_logs:
        for container_name, log_text in container_logs.items():
            hits.extend(
                keyword_service.match_log_text(
                    session=session,
                    namespace=namespace,
                    label_selector=label_selector,
                    pod_name=pod.get("name", ""),
                    container_name=container_name,
                    log_text=log_text,
                )
            )
            hits.extend(
                keyword_service.match_explicit_log_keywords(
                    session=session,
                    namespace=namespace,
                    label_selector=label_selector,
                    pod_name=pod.get("name", ""),
                    container_name=container_name,
                    log_text=log_text,
                    keywords=template_keywords or [],
                )
            )
    else:
        hits = keyword_service.match_log_text(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            pod_name=pod.get("name", ""),
            container_name=(pod.get("containers") or [{}])[0].get("name") if pod.get("containers") else None,
            log_text=pod.get("log_summary"),
        )
        hits.extend(
            keyword_service.match_explicit_log_keywords(
                session=session,
                namespace=namespace,
                label_selector=label_selector,
                pod_name=pod.get("name", ""),
                container_name=(pod.get("containers") or [{}])[0].get("name") if pod.get("containers") else None,
                log_text=pod.get("log_summary"),
                keywords=template_keywords or [],
            )
        )
    pod_copy["log_hits"] = [hit.model_dump() for hit in hits if not hit.whitelisted]
    return pod_copy


def _pod_matches_target(pod: dict, target: dict) -> bool:
    pattern = target.get("pod_name_pattern") or target.get("name")
    return not pattern or fnmatchcase(str(pod.get("name") or ""), str(pattern))


def _scope_text(namespace: str, label_selector: str | None) -> str:
    return f"{namespace}/{label_selector}" if label_selector else namespace


def _build_result_summary(matched: bool, matched_conditions: list[dict], unmatched_conditions: list[dict]) -> str:
    if matched:
        matched_text = "；".join(describe_condition(condition, True) for condition in matched_conditions) or "无明确条件"
        total = len(matched_conditions) + len(unmatched_conditions)
        return f"命中 {len(matched_conditions)}/{total} 个条件：{matched_text}。"

    if unmatched_conditions:
        missing_text = "；".join(describe_condition(condition, False) for condition in unmatched_conditions)
        return f"未命中：{missing_text}。"

    return "未命中：没有满足模板条件。"


def _collection_limits(session: Session) -> CollectionLimits:
    settings = session.get(SystemSetting, 1)
    policy = InspectionPolicySettings.model_validate(
        policy_with_builtin_required_components(settings.inspection_policy if settings else None)
    )
    return CollectionLimits(
        max_log_pods=policy.max_log_pods,
        namespace_concurrency=policy.namespace_concurrency,
    )


def _build_target_context(
    session: Session,
    provider: InspectionProvider,
    template: FaultTemplate,
    log_budget: _DiagnosisLogBudget,
) -> dict:
    limits = log_budget.limits
    targets: dict[str, dict] = {}
    template_keywords_by_target = _template_log_keywords_by_target(template)
    target_definitions: list[tuple[dict, str, str | None, list[dict]]] = []
    for target in template.target_groups:
        namespace = target["namespace"]
        label_selector = target.get("label_selector")
        try:
            inspection = provider.run_namespace_inspection(namespace, label_selector)
        except Exception as error:
            raise RuntimeError(
                f"采集 {_scope_text(namespace, label_selector)} 失败："
                f"{_safe_collection_error(error)}"
            ) from error
        pods = [
            dict(pod)
            for pod in inspection["pods"]
            if _pod_matches_target(pod, target)
        ]
        target_definitions.append((target, namespace, label_selector, pods))
        targets[target["target_ref"]] = {
            "namespace": namespace,
            "label_selector": label_selector,
            "pods": pods,
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }

    targeted_pods_by_namespace: dict[str, set[str]] = {}
    for target, namespace, _, pods in target_definitions:
        if target["target_ref"] not in template_keywords_by_target:
            continue
        targeted_pods_by_namespace.setdefault(namespace, set()).update(
            str(pod.get("name") or "")
            for pod in pods
            if pod.get("name")
        )
    requested_targets = {
        (namespace, pod_name)
        for namespace, pod_names in targeted_pods_by_namespace.items()
        for pod_name in pod_names
    }
    targeted_pod_count = len(log_budget.targeted_pods | requested_targets)
    if targeted_pod_count > limits.max_log_pods:
        raise LogPodLimitExceededError(
            targeted_pod_count,
            limits.max_log_pods,
        )

    for namespace, pod_names in targeted_pods_by_namespace.items():
        new_pod_names = sorted(
            pod_name
            for pod_name in pod_names
            if (namespace, pod_name) not in log_budget.targeted_pods
        )
        if not new_pod_names:
            continue
        remaining_bytes = (
            limits.max_total_log_bytes - log_budget.collected_bytes
        )
        if remaining_bytes < 1024:
            raise RuntimeError("日志采集总字节预算已用尽，请缩小范围")
        namespace_limits = limits.model_copy(
            update={"max_total_log_bytes": remaining_bytes}
        )
        log_collection = provider.collect_pod_log_samples(
            namespace,
            new_pod_names,
            namespace_limits,
        )
        log_budget.collected_bytes += log_collection.collected_log_bytes
        log_budget.targeted_pods.update(
            (namespace, pod_name)
            for pod_name in new_pod_names
        )
        log_budget.samples_by_namespace.setdefault(namespace, {}).update(
            log_collection.container_samples
        )

    for target, namespace, label_selector, pods in target_definitions:
        target_ref = target["target_ref"]
        if target_ref not in template_keywords_by_target:
            continue
        namespace_samples = log_budget.samples_by_namespace.get(namespace, {})
        targets[target_ref]["pods"] = [
            _attach_log_hits(
                session,
                namespace,
                label_selector,
                {
                    **pod,
                    "container_log_summaries": namespace_samples.get(
                        str(pod.get("name") or ""),
                        {},
                    ),
                },
                template_keywords_by_target[target_ref],
            )
            for pod in pods
        ]
    return {"targets": targets}


def _safe_collection_error(error: Exception) -> str:
    if getattr(error, "status", None) == 403:
        group = ""
        kind = ""
        try:
            payload = json.loads(str(getattr(error, "body", "") or "{}"))
            details = payload.get("details") or {}
            group = str(details.get("group") or "")
            kind = str(details.get("kind") or "")
        except (TypeError, ValueError):
            pass
        resource = "/".join(part for part in (group, kind) if part)
        suffix = f"（{resource}）" if resource else ""
        return f"Kubernetes RBAC 权限不足{suffix}，请补充只读 get/list 权限"
    return f"Kubernetes 采集异常（{type(error).__name__}）"


def _build_template_failure_result(template: FaultTemplate, error: Exception) -> dict:
    failure_reason = str(error)
    return {
        "template_id": template.id,
        "template_name": template.name,
        "matched": False,
        "matched_conditions": [],
        "unmatched_conditions": [
            {
                "target_ref": condition.get("target_ref"),
                "condition_type": condition.get("condition_type") or condition.get("type"),
                "operator": condition.get("operator"),
                "expected_value": condition.get("expected_value", condition.get("value")),
                "join_operator": template.joint_rule.get("operator") if template.joint_rule else None,
                "enabled": condition.get("enabled", True),
            }
            for condition in template.match_conditions
        ],
        "summary": f"无法判断：{failure_reason}。",
        "reason": f"模板范围采集失败，暂时无法判断是否命中：{failure_reason}",
        "suggestion": template.suggestion,
        "risk_note": template.risk_note,
        "evidence_refs": [],
    }


def _list_enabled_templates(session: Session, payload: DiagnosisRequest) -> list[FaultTemplate]:
    query = session.query(FaultTemplate).filter(FaultTemplate.enabled.is_(True))
    template_ids = list(payload.template_ids)
    if payload.template_id is not None:
        template_ids.append(payload.template_id)
    if template_ids:
        query = query.filter(FaultTemplate.id.in_(template_ids))
    return query.order_by(FaultTemplate.id.asc()).all()


def run_diagnosis(session: Session, provider: InspectionProvider, payload: DiagnosisRequest) -> dict:
    templates = _list_enabled_templates(session, payload)
    log_budget = _DiagnosisLogBudget(_collection_limits(session))
    matches: list[dict] = []
    template_match_results: list[dict] = []
    evidence_summary: list[dict] = []

    for template in templates:
        try:
            matched = match_template(
                {
                    "target_groups": template.target_groups,
                    "match_conditions": template.match_conditions,
                    "joint_rule": template.joint_rule,
                    "reason": template.reason,
                },
                _build_target_context(
                    session,
                    provider,
                    template,
                    log_budget,
                ),
            )
            template_match_results.append(
                {
                    "template_id": template.id,
                    "template_name": template.name,
                    "matched": matched["matched"],
                    "matched_conditions": [
                        {
                            "target_ref": condition.get("target_ref"),
                            "condition_type": condition.get("condition_type") or condition.get("type"),
                            "operator": condition.get("operator"),
                            "expected_value": condition.get("expected_value", condition.get("value")),
                            "join_operator": template.joint_rule.get("operator") if template.joint_rule else None,
                            "enabled": True,
                        }
                        for condition in matched["matched_conditions"]
                    ],
                    "unmatched_conditions": [
                        {
                            "target_ref": condition.get("target_ref"),
                            "condition_type": condition.get("condition_type") or condition.get("type"),
                            "operator": condition.get("operator"),
                            "expected_value": condition.get("expected_value", condition.get("value")),
                            "join_operator": template.joint_rule.get("operator") if template.joint_rule else None,
                            "enabled": True,
                        }
                        for condition in matched["unmatched_conditions"]
                    ],
                    "summary": _build_result_summary(
                        matched["matched"],
                        matched["matched_conditions"],
                        matched["unmatched_conditions"],
                    ),
                    "reason": template.reason,
                    "suggestion": template.suggestion,
                    "risk_note": template.risk_note,
                    "evidence_refs": matched["evidence"],
                }
            )
            if matched["matched"]:
                evidence_summary.extend(matched["evidence"])
                matches.append(
                    {
                        "template_id": template.id,
                        "template_name": template.name,
                        "reason": template.reason,
                        "suggestion": template.suggestion,
                        "command": template.command,
                        "risk_note": template.risk_note,
                        "evidence": matched["evidence"],
                        "matched_conditions": [
                            _normalize_condition_result(condition, True, [item for item in matched["evidence"] if item.get("type") == (condition.get("type") or condition.get("condition_type"))])
                            for condition in matched["matched_conditions"]
                        ],
                        "unmatched_conditions": [
                            _normalize_condition_result(condition, False, [])
                            for condition in matched["unmatched_conditions"]
                        ],
                    }
                )
        except Exception as error:
            template_match_results.append(_build_template_failure_result(template, error))

    settings = session.get(SystemSetting, 1)
    llm_supplement = None
    status = "matched" if matches else "unmatched"
    if not matches and settings and settings.llm_enabled:
        status = "llm_supplemented"
        llm_supplement = {
            "summary": "规则未命中，建议检查下游依赖与容器启动配置。",
            "confidence": "low",
        }

    template_id = payload.template_id if payload.template_id is not None else (payload.template_ids[0] if payload.template_ids else None)
    result = {
        "status": status,
        "namespace": payload.namespace,
        "direction": payload.direction,
        "scope": payload.scope,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "inspection_target": {
            "type": "namespace" if payload.namespace else "template",
            "namespace": payload.namespace,
            "pod_name": None,
            "label_selector": None,
            "saved_target_id": None,
            "template_id": template_id,
            "resource_scope": ["pods"],
        },
        "matches": matches,
        "template_match_results": template_match_results,
        "evidence_summary": evidence_summary,
        "llm_supplement": llm_supplement,
    }
    persisted_matches = [
        sanitize_persistence_payload(item)
        for item in matches
    ]
    persisted_evidence = [
        sanitize_persistence_payload(item)
        for item in evidence_summary
    ]
    session.add(
        DiagnosisRecord(
            direction=payload.direction,
            request_payload=sanitize_persistence_payload(payload.model_dump()),
            matched_templates=persisted_matches,
            evidence_summary=persisted_evidence,
            status=status,
            llm_result=sanitize_persistence_payload(llm_supplement)
            if llm_supplement
            else None,
        )
    )
    session.commit()
    return sanitize_public_payload(result)


def list_history(session: Session) -> list[DiagnosisRecord]:
    return session.query(DiagnosisRecord).order_by(DiagnosisRecord.executed_at.desc()).all()

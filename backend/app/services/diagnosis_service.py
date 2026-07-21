from datetime import datetime, timezone
from fnmatch import fnmatchcase

from sqlalchemy.orm import Session

from app.engine.matcher import describe_condition, match_template
from app.models import DiagnosisRecord, FaultTemplate, SystemSetting
from app.providers.base import InspectionProvider
from app.schemas.diagnosis import DiagnosisRequest
from app.services import keyword_service


def _normalize_condition_result(condition: dict, matched: bool, evidence: list[dict]) -> dict:
    return {
        "target_ref": condition.get("target_ref"),
        "type": condition.get("type") or condition.get("condition_type"),
        "operator": condition.get("operator"),
        "value": condition.get("value", condition.get("expected_value")),
        "matched": matched,
        "evidence": evidence,
    }


def _attach_log_hits(session: Session, namespace: str, label_selector: str | None, pod: dict) -> dict:
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
    else:
        hits = keyword_service.match_log_text(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            pod_name=pod.get("name", ""),
            container_name=(pod.get("containers") or [{}])[0].get("name") if pod.get("containers") else None,
            log_text=pod.get("log_summary"),
        )
    pod_copy["log_hits"] = [hit.model_dump() for hit in hits]
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


def _build_target_context(session: Session, provider: InspectionProvider, template: FaultTemplate) -> dict:
    targets: dict[str, dict] = {}
    for target in template.target_groups:
        namespace = target["namespace"]
        label_selector = target.get("label_selector")
        try:
            inspection = provider.run_namespace_inspection(namespace, label_selector)
        except Exception as error:
            raise RuntimeError(f"采集 {_scope_text(namespace, label_selector)} 失败，错误：{error}") from error
        targets[target["target_ref"]] = {
            "namespace": namespace,
            "label_selector": label_selector,
            "pods": [
                _attach_log_hits(session, namespace, label_selector, pod)
                for pod in inspection["pods"]
                if _pod_matches_target(pod, target)
            ],
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }
    return {"targets": targets}


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
                _build_target_context(session, provider, template),
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
    session.add(
        DiagnosisRecord(
            direction=payload.direction,
            request_payload=payload.model_dump(),
            matched_templates=matches,
            evidence_summary=evidence_summary,
            status=status,
            llm_result=llm_supplement,
        )
    )
    session.commit()
    return result


def list_history(session: Session) -> list[DiagnosisRecord]:
    return session.query(DiagnosisRecord).order_by(DiagnosisRecord.executed_at.desc()).all()

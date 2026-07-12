from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.engine.matcher import match_template
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
    pod_copy["log_hits"] = [
        hit.model_dump()
        for hit in keyword_service.match_log_text(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            pod_name=pod.get("name", ""),
            container_name=(pod.get("containers") or [{}])[0].get("name") if pod.get("containers") else None,
            log_text=pod.get("log_summary"),
        )
    ]
    return pod_copy


def _build_target_context(session: Session, provider: InspectionProvider, template: FaultTemplate) -> dict:
    targets: dict[str, dict] = {}
    for target in template.target_groups:
        namespace = target["namespace"]
        label_selector = target.get("label_selector")
        inspection = provider.run_namespace_inspection(namespace, label_selector)
        targets[target["target_ref"]] = {
            "namespace": namespace,
            "label_selector": label_selector,
            "pods": [
                _attach_log_hits(session, namespace, label_selector, pod)
                for pod in inspection["pods"]
            ],
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }
    return {"targets": targets}


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
                "summary": f"{template.name} {'命中' if matched['matched'] else '未命中'}",
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

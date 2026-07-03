from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.engine.matcher import match_template
from app.models import DiagnosisRecord, FaultTemplate, SystemSetting
from app.providers.base import InspectionProvider
from app.schemas.diagnosis import DiagnosisRequest


def run_diagnosis(session: Session, provider: InspectionProvider, payload: DiagnosisRequest) -> dict:
    context = provider.collect_diagnosis_context(payload.namespace, payload.scope)
    templates = session.query(FaultTemplate).filter(FaultTemplate.enabled.is_(True)).all()
    matches: list[dict] = []
    evidence_summary: list[dict] = []

    for template in templates:
        matched = match_template(
            {
                "match_conditions": template.match_conditions,
                "reason": template.reason,
            },
            context,
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

    result = {
        "status": status,
        "namespace": payload.namespace,
        "direction": payload.direction,
        "scope": payload.scope,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "matches": matches,
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

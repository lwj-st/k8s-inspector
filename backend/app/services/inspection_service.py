from sqlalchemy.orm import Session

from app.models import InspectionRecord
from app.providers.base import InspectionProvider
from app.schemas.inspection import NamespaceInspectionRequest


def run_cluster_inspection(session: Session, provider: InspectionProvider) -> dict:
    result = provider.run_cluster_inspection()
    session.add(
        InspectionRecord(
            inspection_type="cluster",
            request_payload={},
            result_payload=result,
            summary_status=result["health_status"],
        )
    )
    session.commit()
    return result


def run_namespace_inspection(session: Session, provider: InspectionProvider, payload: NamespaceInspectionRequest) -> dict:
    result = provider.run_namespace_inspection(payload.namespace, payload.label_selector)
    session.add(
        InspectionRecord(
            inspection_type="namespace",
            request_payload=payload.model_dump(),
            result_payload=result,
            summary_status=result["health_status"],
        )
    )
    session.commit()
    return result


def list_history(session: Session, inspection_type: str) -> list[InspectionRecord]:
    return (
        session.query(InspectionRecord)
        .filter(InspectionRecord.inspection_type == inspection_type)
        .order_by(InspectionRecord.executed_at.desc())
        .all()
    )

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_provider
from app.providers.mock_provider import MockInspectionProvider
from app.schemas.diagnosis import DiagnosisRequest, DiagnosisResponse
from app.services import diagnosis_service

router = APIRouter(tags=["diagnoses"])


@router.post("/diagnoses/run", response_model=DiagnosisResponse)
def run_diagnosis(
    payload: DiagnosisRequest,
    session: Session = Depends(get_db_session),
    provider: MockInspectionProvider = Depends(get_provider),
) -> DiagnosisResponse:
    return DiagnosisResponse.model_validate(diagnosis_service.run_diagnosis(session, provider, payload))


@router.get("/diagnoses/history")
def list_diagnosis_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = diagnosis_service.list_history(session)
    return [
        {
            "direction": record.direction,
            "status": record.status,
            "executed_at": record.executed_at.isoformat(),
            "matches": record.matched_templates,
        }
        for record in records
    ]

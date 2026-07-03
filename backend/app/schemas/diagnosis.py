from pydantic import BaseModel, Field


class DiagnosisRequest(BaseModel):
    namespace: str = Field(min_length=1)
    direction: str = "generic"
    scope: str | None = None


class DiagnosisMatch(BaseModel):
    template_id: int
    template_name: str
    reason: str
    suggestion: str
    command: str | None = None
    risk_note: str | None = None
    evidence: list[dict]


class DiagnosisResponse(BaseModel):
    status: str
    namespace: str
    direction: str
    scope: str | None = None
    executed_at: str
    matches: list[DiagnosisMatch]
    evidence_summary: list[dict]
    llm_supplement: dict | None = None

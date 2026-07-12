from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import InspectionTarget, TemplateConditionOperator, TemplateConditionType, TemplateMatchResult


class DiagnosisRequest(BaseModel):
    namespace: str | None = None
    direction: str = "template_check"
    scope: str | None = None
    template_id: int | None = None
    template_ids: list[int] = Field(default_factory=list)


class DiagnosisConditionResult(BaseModel):
    target_ref: str | None = None
    type: TemplateConditionType
    operator: TemplateConditionOperator
    value: Any
    matched: bool
    evidence: list[dict] = Field(default_factory=list)


class DiagnosisMatch(BaseModel):
    template_id: int
    template_name: str
    reason: str
    suggestion: str
    command: str | None = None
    risk_note: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    matched_conditions: list[DiagnosisConditionResult] = Field(default_factory=list)
    unmatched_conditions: list[DiagnosisConditionResult] = Field(default_factory=list)


class DiagnosisResponse(BaseModel):
    status: Literal["matched", "unmatched", "llm_supplemented"]
    namespace: str | None = None
    direction: Literal["template_check"]
    scope: str | None = None
    executed_at: str
    inspection_target: InspectionTarget
    matches: list[DiagnosisMatch] = Field(default_factory=list)
    template_match_results: list[TemplateMatchResult] = Field(default_factory=list)
    evidence_summary: list[dict] = Field(default_factory=list)
    llm_supplement: dict | None = None

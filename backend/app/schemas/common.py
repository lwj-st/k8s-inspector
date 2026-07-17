from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field


class TimestampedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InspectionTargetKind(str, Enum):
    namespace = "namespace"
    pod = "pod"
    template = "template"


class KeywordHitSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class AbnormalCategory(str, Enum):
    pod_status = "pod_status"
    container_status = "container_status"
    event = "event"
    log_keyword = "log_keyword"
    related_object = "related_object"


class TemplateConditionType(str, Enum):
    pod_status = "pod_status"
    log_keyword = "log_keyword"
    event_keyword = "event_keyword"
    restart_count = "restart_count"
    related_object_status = "related_object_status"


class TemplateConditionOperator(str, Enum):
    equals = "equals"
    in_ = "in"
    contains = "contains"
    gte = "gte"
    lte = "lte"


class TemplateConditionJoinOperator(str, Enum):
    AND = "AND"
    OR = "OR"


class InspectionTarget(BaseModel):
    type: InspectionTargetKind
    namespace: str | None = None
    pod_name: str | None = None
    label_selector: str | None = None
    saved_target_id: int | None = None
    template_id: int | None = None
    resource_scope: list[str] = Field(default_factory=list)


class KeywordHit(BaseModel):
    keyword: str
    category: str = "custom"
    severity: KeywordHitSeverity = KeywordHitSeverity.warning
    source: str
    matched_text: str
    container_name: str | None = None
    whitelisted: bool = False
    whitelist_rule_id: int | None = None


class EvidenceBundle(BaseModel):
    object_type: str
    namespace: str
    name: str
    status: str
    node_name: str | None = None
    restarts: int | None = None
    describe_summary: str | None = None
    events: list[str] = Field(default_factory=list)
    resource_usage: dict[str, str] = Field(default_factory=dict)
    log_hits: list[KeywordHit] = Field(default_factory=list)
    related_resources: list[dict[str, Any]] = Field(default_factory=list)


class TemplateTarget(BaseModel):
    target_ref: str = Field(validation_alias=AliasChoices("target_ref", "ref"))
    namespace: str
    label_selector: str | None = None
    pod_name_pattern: str | None = Field(
        default=None,
        validation_alias=AliasChoices("pod_name_pattern", "name"),
    )
    resource_scope: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("resource_scope", "scopes"),
    )

    @computed_field
    @property
    def ref(self) -> str:
        return self.target_ref

    @computed_field
    @property
    def name(self) -> str | None:
        return self.pod_name_pattern

    @computed_field
    @property
    def object_scope(self) -> str | None:
        return self.resource_scope[0] if self.resource_scope else None


class TemplateCondition(BaseModel):
    target_ref: str
    condition_type: TemplateConditionType = Field(validation_alias=AliasChoices("condition_type", "type"))
    operator: TemplateConditionOperator
    expected_value: Any = Field(validation_alias=AliasChoices("expected_value", "value"))
    join_operator: TemplateConditionJoinOperator | None = None
    enabled: bool = True


class TemplateMatchResult(BaseModel):
    template_id: int
    template_name: str
    matched: bool
    matched_conditions: list[TemplateCondition] = Field(default_factory=list)
    unmatched_conditions: list[TemplateCondition] = Field(default_factory=list)
    summary: str | None = None
    reason: str
    suggestion: str
    risk_note: str | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)

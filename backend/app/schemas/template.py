from pydantic import BaseModel, ConfigDict, Field


class FaultTemplateBase(BaseModel):
    name: str = Field(min_length=1)
    scenario: str
    object_scope: str | None = None
    namespace_scope: str | None = None
    label_selector: str | None = None
    match_conditions: list[dict]
    joint_rule: dict | None = None
    reason: str
    suggestion: str
    command: str | None = None
    risk_note: str | None = None
    enabled: bool = True


class FaultTemplateCreate(FaultTemplateBase):
    pass


class FaultTemplateUpdate(FaultTemplateBase):
    pass


class FaultTemplateRead(FaultTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int

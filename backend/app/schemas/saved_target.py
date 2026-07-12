from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class SavedInspectionTargetBase(BaseModel):
    name: str = Field(min_length=1)
    target_type: Literal["namespace", "pod"] = "namespace"
    namespace: str = Field(min_length=1)
    label_selector: str | None = None
    pod_name: str | None = None
    resource_scope: list[str] = Field(default_factory=list)


class SavedInspectionTargetCreate(SavedInspectionTargetBase):
    pass


class SavedInspectionTargetUpdate(SavedInspectionTargetBase):
    pass


class SavedInspectionTargetRead(TimestampedModel, SavedInspectionTargetBase):
    pass

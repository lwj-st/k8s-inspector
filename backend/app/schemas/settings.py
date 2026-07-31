from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.v1_1 import InspectionPolicySettings, RequiredComponentPolicy


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: str = Field(min_length=1, max_length=128)
    base_path: str
    provider_mode: str = "mock"
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    llm_enabled: bool
    llm_provider: str
    model_endpoint: str | None = None
    api_key: str | None = None
    default_inspection_strategy: dict
    inspection_policy: InspectionPolicySettings


class SettingsUpdate(BaseModel):
    cluster_id: str | None = Field(default=None, min_length=1, max_length=128)
    base_path: str
    provider_mode: str = "mock"
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    llm_enabled: bool
    llm_provider: str
    model_endpoint: str | None = None
    api_key: str | None = None
    default_inspection_strategy: dict
    inspection_policy: InspectionPolicySettings | None = None

    @field_validator("cluster_id")
    @classmethod
    def normalize_cluster_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("cluster_id must not be empty")
        return normalized

    @model_validator(mode="after")
    def reject_explicit_null_policy(self) -> "SettingsUpdate":
        if "inspection_policy" in self.model_fields_set and self.inspection_policy is None:
            raise ValueError("inspection_policy must be omitted or contain a complete policy")
        return self


class SystemStatusResponse(BaseModel):
    status: str
    version: str
    message: str
    provider_mode: str
    kube_context: str | None = None


class RequiredComponentCandidate(RequiredComponentPolicy):
    source: str = "discovered"


class RequiredComponentCandidateResponse(BaseModel):
    items: list[RequiredComponentCandidate]

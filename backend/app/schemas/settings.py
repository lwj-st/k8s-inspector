from pydantic import BaseModel, ConfigDict


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_path: str
    provider_mode: str = "mock"
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    llm_enabled: bool
    llm_provider: str
    model_endpoint: str | None = None
    api_key: str | None = None
    default_inspection_strategy: dict


class SettingsUpdate(BaseModel):
    base_path: str
    provider_mode: str = "mock"
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    llm_enabled: bool
    llm_provider: str
    model_endpoint: str | None = None
    api_key: str | None = None
    default_inspection_strategy: dict


class SystemStatusResponse(BaseModel):
    status: str
    version: str
    message: str
    provider_mode: str
    kube_context: str | None = None

from functools import lru_cache
from os import getenv

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "K8s Inspector API"
    base_path: str = ""
    database_url: str = Field(default="sqlite:///./k8s_inspector.db")
    provider_mode: str = "mock"
    frontend_dist_path: str | None = None
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    prefer_incluster: bool = True
    k8s_request_timeout: int = 10
    k8s_log_tail_lines: int = 200
    k8s_log_summary_lines: int = 5
    llm_enabled: bool = False
    llm_provider: str = "qwen"
    model_endpoint: str | None = None
    api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        base_path=getenv("BASE_PATH", ""),
        database_url=getenv("DATABASE_URL", "sqlite:///./k8s_inspector.db"),
        provider_mode=getenv("K8S_PROVIDER_MODE", "mock"),
        frontend_dist_path=getenv("FRONTEND_DIST_PATH"),
        kubeconfig_path=getenv("KUBECONFIG_PATH"),
        kube_context=getenv("KUBECONTEXT"),
        prefer_incluster=getenv("PREFER_INCLUSTER", "true").lower() == "true",
        k8s_request_timeout=int(getenv("K8S_REQUEST_TIMEOUT", "10")),
        k8s_log_tail_lines=int(getenv("K8S_LOG_TAIL_LINES", "200")),
        k8s_log_summary_lines=int(getenv("K8S_LOG_SUMMARY_LINES", "5")),
        llm_enabled=getenv("LLM_ENABLED", "false").lower() == "true",
        llm_provider=getenv("LLM_PROVIDER", "qwen"),
        model_endpoint=getenv("MODEL_ENDPOINT"),
        api_key=getenv("API_KEY"),
    )

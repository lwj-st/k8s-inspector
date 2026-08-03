from functools import lru_cache
from os import getenv

from pydantic import BaseModel, Field, field_validator

from app.core.pathing import normalize_base_path


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = "K8s Inspector API"
    app_version: str = "1.2.0"
    app_env: str = "development"
    cluster_id: str = "local"
    base_path: str = ""
    database_url: str = Field(default="sqlite:///./k8s_inspector.db")
    auto_migrate: bool = True
    provider_mode: str = "mock"
    frontend_dist_path: str | None = None
    kubeconfig_path: str | None = None
    kube_context: str | None = None
    prefer_incluster: bool = True
    k8s_request_timeout: int = 10
    k8s_log_tail_lines: int = 1000
    k8s_log_summary_lines: int = 5
    llm_enabled: bool = False
    llm_provider: str = "qwen"
    model_endpoint: str | None = None
    api_key: str | None = None
    auth_mode: str = "disabled"
    admin_username: str | None = None
    admin_password_hash: str | None = None
    session_secret: str | None = None
    encryption_key: str | None = None
    session_cookie_name: str = "k8s_inspector_session"
    session_idle_minutes: int = Field(default=30, ge=5, le=1440)
    session_absolute_hours: int = Field(default=8, ge=1, le=168)
    session_cookie_secure: bool = False
    login_failure_limit: int = Field(default=5, ge=1, le=100)
    login_failure_window_minutes: int = Field(default=10, ge=1, le=1440)
    trusted_detail_base_url: str | None = None
    webhook_allowed_hosts: list[str] = Field(default_factory=list)
    webhook_allowed_cidrs: list[str] = Field(default_factory=list)

    @field_validator("app_env", "auth_mode", "provider_mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("base_path")
    @classmethod
    def normalize_base_path_value(cls, value: str) -> str:
        return normalize_base_path(value)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def security_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if self.is_production and self.auth_mode == "disabled":
            errors.append("生产环境禁止关闭管理员鉴权")
        if self.auth_mode not in {"disabled", "local"}:
            errors.append("AUTH_MODE 只能为 disabled 或 local")
        if self.auth_mode == "disabled" and self.app_env not in {"development", "test", "ci", "mock"}:
            errors.append("AUTH_MODE=disabled 仅允许 development、test、ci 或 mock 环境")
        if self.auth_mode == "local":
            if not self.admin_username:
                errors.append("缺少管理员用户名")
            if not self.admin_password_hash:
                errors.append("缺少管理员密码哈希")
            else:
                from argon2 import extract_parameters
                from argon2.exceptions import InvalidHashError

                try:
                    extract_parameters(self.admin_password_hash)
                except InvalidHashError:
                    errors.append("管理员密码哈希格式无效")
            if not self.session_secret or len(self.session_secret) < 32:
                errors.append("Session Secret 长度至少为 32 个字符")
        if self.is_production and not self.encryption_key:
            errors.append("缺少敏感配置加密密钥")
        if self.encryption_key:
            from app.security.crypto import SensitiveValueError, SensitiveValueCipher

            try:
                SensitiveValueCipher.from_key(self.encryption_key)
            except SensitiveValueError as exc:
                errors.append(str(exc))
        if self.is_production and not self.session_cookie_secure:
            errors.append("生产环境 Session Cookie 必须启用 Secure")
        if self.is_production and not self.trusted_detail_base_url:
            errors.append("缺少可信详情页基础地址")
        if self.trusted_detail_base_url:
            from app.security.outbound import OutboundTargetError, validate_trusted_detail_base_url

            try:
                validate_trusted_detail_base_url(
                    self.trusted_detail_base_url,
                    production=self.is_production,
                )
            except OutboundTargetError as exc:
                errors.append(str(exc))
        if self.is_production and not (self.webhook_allowed_hosts or self.webhook_allowed_cidrs):
            errors.append("生产环境必须配置 Webhook 目标主机或 CIDR 允许列表")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_version=getenv("APP_VERSION", "1.2.0"),
        app_env=getenv("APP_ENV", "development"),
        cluster_id=getenv("CLUSTER_ID", "local"),
        base_path=getenv("BASE_PATH", ""),
        database_url=getenv("DATABASE_URL", "sqlite:///./k8s_inspector.db"),
        auto_migrate=getenv("AUTO_MIGRATE", "true").lower() == "true",
        provider_mode=getenv("K8S_PROVIDER_MODE", "mock"),
        frontend_dist_path=getenv("FRONTEND_DIST_PATH"),
        kubeconfig_path=getenv("KUBECONFIG_PATH"),
        kube_context=getenv("KUBECONTEXT"),
        prefer_incluster=getenv("PREFER_INCLUSTER", "true").lower() == "true",
        k8s_request_timeout=int(getenv("K8S_REQUEST_TIMEOUT", "10")),
        k8s_log_tail_lines=int(getenv("K8S_LOG_TAIL_LINES", "1000")),
        k8s_log_summary_lines=int(getenv("K8S_LOG_SUMMARY_LINES", "5")),
        llm_enabled=getenv("LLM_ENABLED", "false").lower() == "true",
        llm_provider=getenv("LLM_PROVIDER", "qwen"),
        model_endpoint=getenv("MODEL_ENDPOINT"),
        api_key=getenv("API_KEY"),
        auth_mode=getenv("AUTH_MODE", "disabled"),
        admin_username=getenv("ADMIN_USERNAME"),
        admin_password_hash=getenv("ADMIN_PASSWORD_HASH"),
        session_secret=getenv("SESSION_SECRET"),
        encryption_key=getenv("CONFIG_ENCRYPTION_KEY"),
        session_cookie_name=getenv("SESSION_COOKIE_NAME", "k8s_inspector_session"),
        session_idle_minutes=int(getenv("SESSION_IDLE_MINUTES", "30")),
        session_absolute_hours=int(getenv("SESSION_ABSOLUTE_HOURS", "8")),
        session_cookie_secure=getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        login_failure_limit=int(getenv("LOGIN_FAILURE_LIMIT", "5")),
        login_failure_window_minutes=int(getenv("LOGIN_FAILURE_WINDOW_MINUTES", "10")),
        trusted_detail_base_url=getenv("TRUSTED_DETAIL_BASE_URL"),
        webhook_allowed_hosts=_split_csv(getenv("WEBHOOK_ALLOWED_HOSTS")),
        webhook_allowed_cidrs=_split_csv(getenv("WEBHOOK_ALLOWED_CIDRS")),
    )

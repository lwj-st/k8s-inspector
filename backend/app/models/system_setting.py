from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    base_path: Mapped[str] = mapped_column(String(128), default="")
    provider_mode: Mapped[str] = mapped_column(String(32), default="mock")
    kubeconfig_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    kube_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(64), default="qwen")
    model_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_inspection_strategy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

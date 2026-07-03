from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.models import SystemSetting


def initialize_database(settings: Settings) -> None:
    engine = build_engine(settings)
    Base.metadata.create_all(bind=engine)
    _ensure_system_settings_columns(engine)

    with Session(engine) as session:
        existing = session.scalar(select(SystemSetting).where(SystemSetting.id == 1))
        if existing is None:
            session.add(
                SystemSetting(
                    id=1,
                    base_path=settings.base_path,
                    provider_mode=settings.provider_mode,
                    kubeconfig_path=settings.kubeconfig_path,
                    kube_context=settings.kube_context,
                    llm_enabled=settings.llm_enabled,
                    llm_provider=settings.llm_provider,
                    model_endpoint=settings.model_endpoint,
                    api_key=settings.api_key,
                    default_inspection_strategy={},
                )
            )
            session.commit()


def _ensure_system_settings_columns(engine) -> None:
    expected_columns = {
        "provider_mode": "ALTER TABLE system_settings ADD COLUMN provider_mode VARCHAR(32) DEFAULT 'mock'",
        "kubeconfig_path": "ALTER TABLE system_settings ADD COLUMN kubeconfig_path VARCHAR(512)",
        "kube_context": "ALTER TABLE system_settings ADD COLUMN kube_context VARCHAR(255)",
    }
    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(system_settings)"))
        }
        for column, ddl in expected_columns.items():
            if column not in existing:
                connection.execute(text(ddl))

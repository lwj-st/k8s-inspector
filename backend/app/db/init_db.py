from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.models import SystemSetting
from app.schemas.v1_1 import InspectionPolicySettings, default_required_components
from app.security.crypto import SensitiveValueCipher
from app.services.keyword_service import ensure_default_keywords


def initialize_database(settings: Settings) -> None:
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            existing = session.scalar(select(SystemSetting).where(SystemSetting.id == 1))
            if existing is None:
                encrypted_api_key = None
                if settings.api_key:
                    encrypted_api_key = SensitiveValueCipher.from_key(settings.encryption_key).encrypt(
                        settings.api_key,
                        purpose="llm_api_key",
                    )
                session.add(
                    SystemSetting(
                        id=1,
                        cluster_id=settings.cluster_id,
                        base_path=settings.base_path,
                        provider_mode=settings.provider_mode,
                        kubeconfig_path=settings.kubeconfig_path,
                        kube_context=settings.kube_context,
                        llm_enabled=settings.llm_enabled,
                        llm_provider=settings.llm_provider,
                        model_endpoint=settings.model_endpoint,
                        api_key=None,
                        api_key_encrypted=encrypted_api_key,
                        admin_password_hash=settings.admin_password_hash,
                        default_inspection_strategy={},
                        inspection_policy=InspectionPolicySettings(
                            required_components=default_required_components(),
                        ).model_dump(mode="json"),
                    )
                )
                session.commit()
            ensure_default_keywords(session)
    finally:
        engine.dispose()

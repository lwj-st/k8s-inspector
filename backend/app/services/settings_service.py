from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import SystemSetting
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.schemas.v1_1 import InspectionPolicySettings
from app.security.crypto import SensitiveValueCipher


MASKED_SECRET = "********"


def get_settings(session: Session) -> SystemSetting:
    settings = session.get(SystemSetting, 1)
    if settings is None:
        raise ValueError("settings not found")
    return settings


def serialize_settings(settings: SystemSetting) -> SettingsResponse:
    policy = settings.inspection_policy or InspectionPolicySettings().model_dump(mode="json")
    return SettingsResponse(
        base_path=settings.base_path,
        provider_mode=settings.provider_mode,
        kubeconfig_path=settings.kubeconfig_path,
        kube_context=settings.kube_context,
        llm_enabled=settings.llm_enabled,
        llm_provider=settings.llm_provider,
        model_endpoint=settings.model_endpoint,
        api_key=MASKED_SECRET if settings.api_key_encrypted else None,
        default_inspection_strategy=settings.default_inspection_strategy,
        inspection_policy=InspectionPolicySettings.model_validate(policy),
    )


def update_settings(
    session: Session,
    payload: SettingsUpdate,
    app_settings: Settings,
) -> SystemSetting:
    settings = get_settings(session)
    values = payload.model_dump(exclude={"api_key", "inspection_policy"})
    for key, value in values.items():
        setattr(settings, key, value)
    if payload.api_key != MASKED_SECRET:
        settings.api_key = None
        settings.api_key_encrypted = (
            SensitiveValueCipher.from_key(app_settings.encryption_key).encrypt(
                payload.api_key,
                purpose="llm_api_key",
            )
            if payload.api_key
            else None
        )
    if "inspection_policy" in payload.model_fields_set:
        settings.inspection_policy = payload.inspection_policy.model_dump(mode="json")
    session.commit()
    session.refresh(settings)
    return settings

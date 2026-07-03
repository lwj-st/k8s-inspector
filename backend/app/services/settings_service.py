from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.schemas.settings import SettingsUpdate


def get_settings(session: Session) -> SystemSetting:
    settings = session.get(SystemSetting, 1)
    if settings is None:
        raise ValueError("settings not found")
    return settings


def update_settings(session: Session, payload: SettingsUpdate) -> SystemSetting:
    settings = get_settings(session)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    session.commit()
    session.refresh(settings)
    return settings

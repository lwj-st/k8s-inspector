from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.pathing import build_api_prefix
from app.db.init_db import initialize_database
from app.db.session import build_session_factory
from app.providers.factory import build_provider


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    initialize_database(current_settings)
    session_factory = build_session_factory(current_settings)
    provider = build_provider(current_settings)

    app = FastAPI(title=current_settings.app_name)
    app.state.settings = current_settings
    app.state.session_factory = session_factory
    app.state.provider = provider
    app.include_router(build_api_router(), prefix=build_api_prefix(current_settings.base_path))

    return app


app = create_app()

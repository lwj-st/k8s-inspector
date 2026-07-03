from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.pathing import build_api_prefix
from app.core.runtime_paths import resolve_frontend_dist_path
from app.db.init_db import initialize_database
from app.db.session import build_session_factory
from app.providers.factory import build_provider


def register_frontend(app: FastAPI, settings: Settings) -> None:
    dist_path = resolve_frontend_dist_path(settings.frontend_dist_path)
    if not dist_path:
        return

    base_path = settings.base_path.rstrip("/")
    assets_path = dist_path / "assets"
    mount_prefix = f"{base_path}/assets" if base_path else "/assets"

    if assets_path.exists():
        app.mount(mount_prefix, StaticFiles(directory=assets_path), name=f"assets{base_path or 'root'}")

    index_path = dist_path / "index.html"
    if not index_path.exists():
        return

    @app.get(f"{base_path}/{{full_path:path}}" if base_path else "/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str = "") -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path and not full_path.startswith("api/"):
            target = dist_path / full_path
            if target.exists() and target.is_file():
                return FileResponse(target)
        return FileResponse(index_path)


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
    register_frontend(app, current_settings)

    return app


app = create_app()

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import build_api_router
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.pathing import build_api_prefix, normalize_base_path
from app.core.runtime_paths import resolve_frontend_dist_path
from app.db.init_db import initialize_database
from app.db.migrate import HEAD_REVISION, current_revision, upgrade_database
from app.db.session import build_session_factory
from app.providers.factory import build_provider
from app.security.lifespan import build_lifespan
from app.security.middleware import AuthenticationMiddleware
from app.security.component_status import ComponentStatusRegistry
from app.security.errors import register_api_error_handlers


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
    platform_initialization_error = None
    try:
        if current_settings.auto_migrate:
            upgrade_database(current_settings)
        elif current_revision(current_settings) != HEAD_REVISION:
            raise RuntimeError("数据库 migration 尚未执行")
        initialize_database(current_settings)
    except Exception as exc:
        platform_initialization_error = f"平台初始化失败：{type(exc).__name__}"
    session_factory = build_session_factory(current_settings)
    provider = None
    provider_initialization_error = None
    try:
        provider = build_provider(current_settings)
    except Exception as exc:
        provider_initialization_error = f"Provider 初始化失败：{type(exc).__name__}"

    app = FastAPI(
        title=current_settings.app_name,
        version=current_settings.app_version,
        lifespan=build_lifespan(),
        docs_url=None if current_settings.is_production else "/docs",
        redoc_url=None if current_settings.is_production else "/redoc",
        openapi_url=None if current_settings.is_production else "/openapi.json",
    )
    app.state.settings = current_settings
    app.state.session_factory = session_factory
    app.state.provider = provider
    app.state.provider_initialization_error = provider_initialization_error
    app.state.platform_initialization_error = platform_initialization_error
    app.state.lifespan_hook_error = None
    app.state.component_status_registry = ComponentStatusRegistry()
    app.add_middleware(AuthenticationMiddleware, settings=current_settings)
    register_api_error_handlers(app)
    app.include_router(build_api_router(), prefix=build_api_prefix(current_settings.base_path))
    app.include_router(health.router, prefix=normalize_base_path(current_settings.base_path))
    register_frontend(app, current_settings)

    return app


app = create_app()

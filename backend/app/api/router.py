from fastapi import APIRouter

from app.api.routes import diagnoses
from app.api.routes import discovery
from app.api.routes import inspections
from app.api.routes import keywords
from app.api.routes import overview
from app.api.routes import saved_targets
from app.api.routes import settings
from app.api.routes import templates
from app.api.routes import whitelists


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(discovery.router)
    router.include_router(overview.router)
    router.include_router(inspections.router)
    router.include_router(diagnoses.router)
    router.include_router(keywords.router)
    router.include_router(saved_targets.router)
    router.include_router(templates.router)
    router.include_router(whitelists.router)
    router.include_router(settings.router)
    return router

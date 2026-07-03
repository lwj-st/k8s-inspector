from fastapi import APIRouter

from app.api.routes import diagnoses, inspections, overview, settings, templates, whitelists


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(overview.router)
    router.include_router(inspections.router)
    router.include_router(diagnoses.router)
    router.include_router(templates.router)
    router.include_router(whitelists.router)
    router.include_router(settings.router)
    return router

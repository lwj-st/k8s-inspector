from app.providers.base import InspectionProvider


def get_overview(provider: InspectionProvider) -> dict:
    return provider.get_overview()

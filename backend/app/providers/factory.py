from app.core.config import Settings
from app.providers.kubernetes_provider import KubernetesInspectionProvider
from app.providers.mock_provider import MockInspectionProvider


def build_provider(settings: Settings):
    if settings.provider_mode == "kubernetes":
        return KubernetesInspectionProvider(settings)
    return MockInspectionProvider()

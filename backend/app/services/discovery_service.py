from app.providers.base import InspectionProvider


def discover_namespaces(provider: InspectionProvider) -> dict:
    result = provider.list_namespaces()
    namespaces = sorted(result.get("namespaces", []), key=lambda item: str(item.get("name", "")))
    return {
        "executed_at": result["executed_at"],
        "namespaces": namespaces,
    }

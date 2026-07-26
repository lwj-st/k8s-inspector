from app.providers.base import InspectionProvider


def discover_namespaces(provider: InspectionProvider) -> dict:
    result = provider.list_namespaces()
    namespaces = sorted(result.get("namespaces", []), key=lambda item: str(item.get("name", "")))
    return {
        "executed_at": result["executed_at"],
        "namespaces": namespaces,
    }


def discover_namespace_labels(provider: InspectionProvider, namespace: str) -> dict:
    result = provider.list_namespace_labels(namespace)
    labels = sorted(
        result.get("labels", []),
        key=lambda item: (str(item.get("key", "")), str(item.get("selector", ""))),
    )
    return {
        "namespace": namespace,
        "executed_at": result["executed_at"],
        "labels": labels,
    }


def discover_namespace_pods(
    provider: InspectionProvider,
    namespace: str,
    label_selector: str | None = None,
) -> dict:
    result = provider.list_namespace_pods(namespace, label_selector)
    pods = sorted(
        result.get("pods", []),
        key=lambda item: str(item.get("name", "")),
    )
    return {
        "namespace": namespace,
        "label_selector": label_selector,
        "executed_at": result["executed_at"],
        "pod_count": len(pods),
        "pods": pods,
    }

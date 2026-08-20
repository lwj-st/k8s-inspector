from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.providers.base import InspectionProvider


class ImageInventoryScopeError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_image(value: str | None) -> str:
    return (value or "").strip()


def build_inventory(
    provider: InspectionProvider,
    *,
    namespaces: list[str],
    search: str | None = None,
) -> dict:
    requested_namespaces = _normalize_namespaces(namespaces)
    if not requested_namespaces:
        raise ImageInventoryScopeError("请选择名称空间后查看镜像清单")

    search_text = (search or "").strip()
    search_lower = search_text.lower()
    references_by_image: dict[str, list[dict]] = defaultdict(list)
    provider_mode = "unknown"
    simulated = False

    for namespace in requested_namespaces:
        snapshot = provider.list_namespace_pod_images(namespace)
        provider_mode = str(snapshot.get("provider_mode") or provider_mode)
        simulated = simulated or bool(snapshot.get("simulated"))
        for pod in snapshot.get("pods", []):
            pod_name = str(pod.get("name") or "")
            pod_phase = str(pod.get("phase") or "Unknown")
            pod_created_at = pod.get("created_at")
            for raw_ref in pod.get("images", []):
                image = normalize_image(raw_ref.get("image"))
                if not image:
                    continue
                if search_lower and search_lower not in image.lower():
                    continue
                references_by_image[image].append(
                    {
                        "namespace": namespace,
                        "pod_name": pod_name,
                        "pod_phase": pod_phase,
                        "container_name": str(raw_ref.get("container_name") or ""),
                        "container_type": str(raw_ref.get("container_type") or "container"),
                        "source": str(raw_ref.get("source") or "spec"),
                        "image": image,
                        "image_id": normalize_image(raw_ref.get("image_id")) or None,
                        "pod_created_at": pod_created_at,
                    }
                )

    items = [_build_item(image, refs) for image, refs in references_by_image.items()]
    items.sort(key=lambda item: item["image"])
    summary = _build_summary(items)
    return {
        "executed_at": _now_iso(),
        "namespaces": requested_namespaces,
        "search": search_text or None,
        "provider_mode": provider_mode,
        "simulated": simulated,
        "summary": summary,
        "items": items,
    }


def export_inventory_text(inventory: dict) -> str:
    return "\n".join(item["image"] for item in inventory["items"])


def _normalize_namespaces(namespaces: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for namespace in namespaces:
        value = namespace.strip()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _build_item(image: str, refs: list[dict]) -> dict:
    refs.sort(
        key=lambda ref: (
            ref["namespace"],
            ref["pod_name"],
            ref["container_name"],
            ref["source"],
        )
    )
    namespaces = {ref["namespace"] for ref in refs}
    pods = {(ref["namespace"], ref["pod_name"]) for ref in refs}
    containers = {
        (ref["namespace"], ref["pod_name"], ref["container_name"], ref["container_type"])
        for ref in refs
    }
    latest_ref = max(
        (ref for ref in refs if ref.get("pod_created_at")),
        key=lambda ref: str(ref.get("pod_created_at")),
        default=None,
    )
    return {
        "image": image,
        "namespace_count": len(namespaces),
        "pod_count": len(pods),
        "container_count": len(containers),
        "latest_pod_created_at": latest_ref.get("pod_created_at") if latest_ref else None,
        "latest_pod_phase": latest_ref.get("pod_phase") if latest_ref else None,
        "references": refs,
    }


def _build_summary(items: list[dict]) -> dict:
    namespaces = {
        ref["namespace"]
        for item in items
        for ref in item["references"]
    }
    pods = {
        (ref["namespace"], ref["pod_name"])
        for item in items
        for ref in item["references"]
    }
    containers = {
        (ref["namespace"], ref["pod_name"], ref["container_name"], ref["container_type"])
        for item in items
        for ref in item["references"]
    }
    return {
        "image_count": len(items),
        "namespace_count": len(namespaces),
        "pod_count": len(pods),
        "container_count": len(containers),
    }

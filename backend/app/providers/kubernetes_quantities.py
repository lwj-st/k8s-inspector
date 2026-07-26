"""Kubernetes CPU/memory quantity parsing used by status and metrics checks."""

from __future__ import annotations

from typing import Any


def quantity_cpu_millicores(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    text = str(value)
    try:
        if text.endswith("n"):
            return int(float(text[:-1]) / 1_000_000)
        if text.endswith("u"):
            return int(float(text[:-1]) / 1_000)
        if text.endswith("m"):
            return int(float(text[:-1]))
        return int(float(text) * 1000)
    except ValueError:
        return None


def quantity_bytes(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    text = str(value)
    binary = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }
    decimal = {"K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4}
    try:
        for suffix, multiplier in binary.items():
            if text.endswith(suffix):
                return int(float(text[: -len(suffix)]) * multiplier)
        for suffix, multiplier in decimal.items():
            if text.endswith(suffix):
                return int(float(text[: -len(suffix)]) * multiplier)
        return int(float(text))
    except ValueError:
        return None


def sum_resources(pod: Any, field: str) -> tuple[int, int]:
    """Return the Pod's scheduling CPU/memory requests or limits."""

    spec = getattr(pod, "spec", None)
    regular_cpu = regular_memory = 0
    for container in getattr(spec, "containers", None) or []:
        values = getattr(getattr(container, "resources", None), field, None) or {}
        regular_cpu += quantity_cpu_millicores(values.get("cpu")) or 0
        regular_memory += quantity_bytes(values.get("memory")) or 0
    init_cpu = init_memory = 0
    for container in getattr(spec, "init_containers", None) or []:
        values = getattr(getattr(container, "resources", None), field, None) or {}
        init_cpu = max(init_cpu, quantity_cpu_millicores(values.get("cpu")) or 0)
        init_memory = max(init_memory, quantity_bytes(values.get("memory")) or 0)
    overhead = getattr(spec, "overhead", None) or {}
    return (
        max(regular_cpu, init_cpu)
        + (quantity_cpu_millicores(overhead.get("cpu")) or 0),
        max(regular_memory, init_memory)
        + (quantity_bytes(overhead.get("memory")) or 0),
    )

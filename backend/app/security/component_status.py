from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from app.schemas.v1_1 import ComponentState, SystemComponentStatus


_UPDATABLE_COMPONENTS = {
    "kubernetes_api",
    "scheduler",
    "metrics_api",
    "notifications",
    "last_inspection",
}


class ComponentStatusRegistry:
    """Thread-safe, schema-validated status bridge for later v1.1 modules."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._statuses = {
            name: _unavailable(message)
            for name, message in {
                "kubernetes_api": "Kubernetes API 尚未探测",
                "scheduler": "调度器尚未注册",
                "metrics_api": "Metrics API 为可选能力，尚未探测",
                "notifications": "通知渠道尚未加载",
                "last_inspection": "暂无 v1.1 巡检执行状态",
            }.items()
        }
        self._kubernetes_server_version: str | None = None
        self._kubernetes_version_supported: bool | None = None

    def update(self, component: str, status: SystemComponentStatus) -> None:
        if component not in _UPDATABLE_COMPONENTS:
            raise ValueError(f"不允许更新系统组件状态：{component}")
        validated = SystemComponentStatus.model_validate(status)
        with self._lock:
            self._statuses[component] = validated.model_copy(deep=True)

    def get(self, component: str) -> SystemComponentStatus:
        if component not in _UPDATABLE_COMPONENTS:
            raise ValueError(f"未知系统组件状态：{component}")
        with self._lock:
            return self._statuses[component].model_copy(deep=True)

    def update_kubernetes_version(self, version: str | None, supported: bool | None) -> None:
        normalized = version.strip() if version else None
        if normalized and len(normalized) > 64:
            raise ValueError("Kubernetes 版本字符串过长")
        if normalized is None and supported is not None:
            raise ValueError("未提供 Kubernetes 版本时不能设置兼容状态")
        with self._lock:
            self._kubernetes_server_version = normalized
            self._kubernetes_version_supported = supported

    def kubernetes_version(self) -> tuple[str | None, bool | None]:
        with self._lock:
            return self._kubernetes_server_version, self._kubernetes_version_supported


def _unavailable(message: str) -> SystemComponentStatus:
    return SystemComponentStatus(
        state=ComponentState.unavailable,
        message=message,
        checked_at=datetime.now(timezone.utc),
        details={},
    )

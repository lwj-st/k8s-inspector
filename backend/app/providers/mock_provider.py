from datetime import datetime, timezone

from app.providers.base import LogPodLimitExceededError, TemporaryPodLogCollection
from app.schemas.v1_1 import (
    CollectionLayer,
    CollectionLimits,
    ProviderCollectionFailure,
    ProviderCollectionRequest,
    ProviderCollectionResult,
    ProviderObservation,
    ResourceRef,
)
from app.services.pod_health import is_abnormal_pod


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_log_hit(keyword: str, matched_text: str, *, container_name: str = "demo-api") -> dict:
    return {
        "keyword": keyword,
        "category": "dependency",
        "severity": "warning",
        "source": "current_log",
        "matched_text": matched_text,
        "container_name": container_name,
        "whitelisted": False,
        "whitelist_rule_id": None,
    }


def build_evidence_bundle(namespace: str, pod: dict) -> dict:
    log_hits = []
    log_summary = str(pod.get("log_summary") or "")
    if "connection refused" in log_summary:
        log_hits.append(build_log_hit("connection refused", log_summary))
    return {
        "object_type": "pod",
        "namespace": namespace,
        "name": pod["name"],
        "status": pod["status"],
        "node_name": pod.get("node_name"),
        "restarts": pod.get("restarts"),
        "describe_summary": pod.get("describe_summary"),
        "events": pod.get("events", []),
        "resource_usage": pod.get("resource_usage", {}),
        "log_hits": log_hits,
        "related_resources": pod.get("related_resources", []),
    }


def build_demo_pod(pod_name: str = "demo-api-7c8f6f7c6b-fh2ns") -> dict:
    return {
        "name": pod_name,
        "labels": {"app": "demo"},
        "status": "CrashLoopBackOff",
        "node_name": "node-a",
        "restarts": 6,
        "containers": [
            {
                "name": "demo-api",
                "restart_count": 6,
                "state": "waiting",
                "reason": "CrashLoopBackOff",
            }
        ],
        "events": ["Back-off restarting failed container"],
        "describe_summary": "容器启动后健康检查失败并退出。",
        "log_summary": "database connection refused",
        "previous_log_summary": "previous crash: database connection refused",
        "resource_usage": {"cpu": "220m", "memory": "180Mi"},
        "related_resources": [{"kind": "Service", "name": "demo-api", "status": "healthy"}],
    }


class MockInspectionProvider:
    def collect_resources(
        self,
        request: ProviderCollectionRequest,
    ) -> ProviderCollectionResult:
        observed_at = datetime.now(timezone.utc)
        namespace = request.scope.namespace or (
            request.scope.namespaces[0] if request.scope.namespaces else "demo"
        )
        if request.layer == CollectionLayer.evidence:
            return ProviderCollectionResult(
                layer=request.layer,
                evidence=[],
                kubernetes_api_calls=len(request.evidence_targets),
                log_pods_read=0,
                collected_log_bytes=0,
                duration_ms=8,
            )
        observations = [
            ProviderObservation(
                resource=ResourceRef(kind="KubernetesVersion", name="server"),
                observed_at=observed_at,
                observed_state="v1.36.0",
                facts={
                    "major": 1,
                    "minor": 36,
                    "supported": True,
                    "supported_range": "1.34-1.36",
                },
            ),
            ProviderObservation(
                resource=ResourceRef(
                    kind="Deployment",
                    namespace=namespace,
                    name="demo-api",
                ),
                observed_at=observed_at,
                observed_state="active",
                facts={
                    "desired": 3,
                    "ready": 1,
                    "available": 1,
                    "updated": 1,
                    "paused": False,
                    "labels": ["app=demo-api"],
                },
            ),
            ProviderObservation(
                resource=ResourceRef(
                    kind="Pod",
                    namespace=namespace,
                    name="demo-api-0",
                ),
                observed_at=observed_at,
                observed_state="Running",
                facts={
                    "phase": "Running",
                    "ready": False,
                    "restart_delta": 0,
                    "warning_reasons": [],
                    "missing_references": [],
                },
            ),
            ProviderObservation(
                resource=ResourceRef(
                    kind="Service",
                    namespace=namespace,
                    name="demo-api",
                ),
                observed_at=observed_at,
                observed_state="ClusterIP",
                facts={
                    "service_type": "ClusterIP",
                    "selector_present": True,
                    "selector": ["app=demo-api"],
                    "selected_pods": 1,
                    "endpoint_slices": 1,
                    "ready_endpoints": 0,
                    "ingress_referenced": False,
                },
            ),
        ]
        return ProviderCollectionResult(
            layer=request.layer,
            observations=observations,
            failures=[
                ProviderCollectionFailure(
                    check_code="storage.status",
                    error_code="MOCK_STORAGE_PARTIAL",
                    message="Mock：存储 API 局部失败",
                )
            ],
            kubernetes_api_calls=7,
            log_pods_read=0,
            collected_log_bytes=0,
            duration_ms=12,
        )

    def list_namespaces(self) -> dict:
        return {
            "executed_at": now_iso(),
            "namespaces": [
                {
                    "name": "demo",
                    "status": "warning",
                    "pod_count": 1,
                    "abnormal_pod_count": 1,
                    "last_inspected_at": now_iso(),
                    "labels": {"team": "platform"},
                    "abnormal_categories": ["pod_status", "log_keyword"],
                },
                {
                    "name": "prod-core",
                    "status": "healthy",
                    "pod_count": 4,
                    "abnormal_pod_count": 0,
                    "last_inspected_at": now_iso(),
                    "labels": {"team": "platform", "environment": "production"},
                    "abnormal_categories": [],
                },
                {
                    "name": "kube-system",
                    "status": "healthy",
                    "pod_count": 6,
                    "abnormal_pod_count": 0,
                    "last_inspected_at": now_iso(),
                    "labels": {"team": "infrastructure"},
                    "abnormal_categories": [],
                },
            ],
        }

    def list_namespace_labels(self, namespace: str) -> dict:
        labels_by_namespace = {
            "demo": [
                {"key": "team", "value": "platform", "pod_count": 1},
                {"key": "app", "value": "demo-api", "pod_count": 1},
            ],
            "prod-core": [
                {"key": "team", "value": "platform", "pod_count": 4},
                {"key": "environment", "value": "production", "pod_count": 4},
            ],
            "kube-system": [
                {"key": "team", "value": "infrastructure", "pod_count": 6},
            ],
        }
        labels = labels_by_namespace.get(namespace, [])
        return {
            "namespace": namespace,
            "executed_at": now_iso(),
            "labels": [
                {
                    "key": item["key"],
                    "values": [item["value"]],
                    "selector": f'{item["key"]}={item["value"]}',
                    "pod_count": item["pod_count"],
                }
                for item in labels
            ],
        }

    def list_namespace_pods(
        self,
        namespace: str,
        label_selector: str | None = None,
    ) -> dict:
        pod = build_demo_pod()
        return {
            "namespace": namespace,
            "label_selector": label_selector,
            "executed_at": now_iso(),
            "pod_count": 1,
            "pods": [
                {
                    "name": pod["name"],
                    "labels": dict(pod["labels"]),
                }
            ],
        }

    def get_overview(self) -> dict:
        return {
            "health_status": "warning",
            "health_score": 72,
            "last_checked_at": now_iso(),
            "recent_summary": "发现 ingress-nginx 和 demo 命名空间存在异常。",
            "issues": [
                {
                    "name": "ingress-nginx-controller",
                    "namespace": "ingress-nginx",
                    "node": "node-a",
                    "status": "degraded",
                    "summary": "控制器 Pod 重启次数过高。",
                }
            ],
        }

    def run_cluster_inspection(
        self,
        *,
        include_logs: bool = False,
    ) -> dict:
        return {
            "health_status": "warning",
            "executed_at": now_iso(),
            "results": [
                {
                    "component": "ingress-nginx",
                    "namespace": "ingress-nginx",
                    "node": "node-a",
                    "status": "degraded",
                    "describe_summary": "Pod 重启 4 次，最近一次因为配置加载失败退出。",
                    "log_summary": (
                        "failed to load default backend"
                        if include_logs
                        else None
                    ),
                }
            ],
        }

    def run_namespace_inspection(
        self,
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = False,
        limits: CollectionLimits | None = None,
    ) -> dict:
        pod = build_demo_pod()
        if not include_logs:
            pod["events"] = []
            pod["log_summary"] = None
            pod["previous_log_summary"] = None
        pods = [pod]
        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": "warning",
            "executed_at": now_iso(),
            "evidence_bundles": [build_evidence_bundle(namespace, pod) for pod in pods],
            "pods": pods,
            "services": [
                {"name": "demo-api", "status": "healthy", "summary": "ClusterIP 正常"}
            ],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }

    def collect_pod_log_samples(
        self,
        namespace: str,
        pod_names: list[str],
        limits: CollectionLimits,
    ) -> TemporaryPodLogCollection:
        unique_names = list(dict.fromkeys(name for name in pod_names if name))
        if len(unique_names) > limits.max_log_pods:
            raise LogPodLimitExceededError(len(unique_names), limits.max_log_pods)
        container_samples: dict[str, dict[str, str]] = {}
        collected_bytes = 0
        truncated = False
        for pod_name in unique_names:
            raw = str(build_demo_pod(pod_name)["log_summary"] or "")
            allowed = min(
                limits.max_log_bytes_per_pod,
                limits.max_total_log_bytes - collected_bytes,
            )
            if allowed <= 0:
                truncated = True
                break
            encoded = raw.encode("utf-8")
            sample = encoded[:allowed].decode("utf-8", errors="ignore")
            collected_bytes += min(len(encoded), allowed)
            truncated = truncated or len(encoded) > allowed
            if sample:
                container_samples[pod_name] = {"demo-api": sample}
        return TemporaryPodLogCollection(
            container_samples=container_samples,
            log_pods_read=len(container_samples),
            collected_log_bytes=collected_bytes,
            truncated=truncated,
        )

    def run_pod_inspection(self, namespace: str, pod_name: str) -> dict:
        pod = build_demo_pod(pod_name)
        if pod["name"] != pod_name:
            raise LookupError(f"pod {namespace}/{pod_name} not found")
        return {
            "inspection_target": {
                "type": "pod",
                "namespace": namespace,
                "pod_name": pod_name,
                "resource_scope": ["pods"],
            },
            "namespace": namespace,
            "health_status": "warning" if is_abnormal_pod(pod) else "healthy",
            "executed_at": now_iso(),
            "pod": pod,
            "evidence_bundle": build_evidence_bundle(namespace, pod),
        }

    def collect_diagnosis_context(self, namespace: str, scope: str | None) -> dict:
        inspection = self.run_namespace_inspection(namespace, None)
        pods = inspection["pods"]
        if scope and "/" in scope:
            scope_kind, scope_name = scope.split("/", 1)
            if scope_kind == "pod":
                pods = [pod for pod in pods if pod["name"] == scope_name]
            else:
                prefix = f"{scope_name}-"
                pods = [pod for pod in pods if pod["name"] == scope_name or pod["name"].startswith(prefix)]
        return {
            "namespace": namespace,
            "scope": scope,
            "pods": pods,
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }

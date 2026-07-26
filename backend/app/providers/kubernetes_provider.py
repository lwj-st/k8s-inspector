from __future__ import annotations

import ast
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from app.core.config import Settings
from app.providers.base import LogPodLimitExceededError, TemporaryPodLogCollection
from app.providers.kubernetes_collection import KubernetesResourceCollector
from app.schemas.v1_1 import CollectionLimits, ProviderCollectionRequest, ProviderCollectionResult
from app.services.pod_health import is_abnormal_container, is_abnormal_pod, is_normal_pod_status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_int(settings: Settings, name: str, default: int) -> int:
    return int(getattr(settings, name, default) or default)


class KubernetesInspectionProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._load_config()
        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()
        self.batch = client.BatchV1Api()
        self.networking = client.NetworkingV1Api()
        self.discovery = client.DiscoveryV1Api()
        self.storage = client.StorageV1Api()
        self.custom = client.CustomObjectsApi()
        self.version_api = client.VersionApi()
        self.api_client = ApiClient()
        self._resource_collector = self._build_resource_collector()

    def _build_resource_collector(self) -> KubernetesResourceCollector:
        return KubernetesResourceCollector(
            settings=self.settings,
            core=self.core,
            apps=self.apps,
            batch=self.batch,
            networking=self.networking,
            discovery=self.discovery,
            storage=self.storage,
            custom=self.custom,
            version_api=self.version_api,
        )

    def collect_resources(
        self,
        request: ProviderCollectionRequest,
    ) -> ProviderCollectionResult:
        return self._get_resource_collector().collect(request)

    def _get_resource_collector(self) -> KubernetesResourceCollector:
        collector = getattr(self, "_resource_collector", None)
        if collector is None:
            collector = self._build_resource_collector()
            self._resource_collector = collector
        return collector

    def _load_config(self) -> None:
        if self.settings.kubeconfig_path:
            config.load_kube_config(
                config_file=self.settings.kubeconfig_path,
                context=self.settings.kube_context,
            )
            return

        if self.settings.prefer_incluster:
            try:
                config.load_incluster_config()
                return
            except ConfigException:
                pass

        raise ValueError("No Kubernetes client configuration available")

    def _serialize(self, obj: object) -> str:
        return str(self.api_client.sanitize_for_serialization(obj))

    def _is_abnormal_pod(self, pod: client.V1Pod) -> bool:
        phase = pod.status.phase or "Unknown"
        if not is_normal_pod_status(phase):
            return True
        if phase == "Running":
            ready = next(
                (
                    condition
                    for condition in getattr(pod.status, "conditions", None) or []
                    if condition.type == "Ready"
                ),
                None,
            )
            if ready is not None and ready.status != "True":
                return True
        for status in (
            list(getattr(pod.status, "init_container_statuses", None) or [])
            + list(getattr(pod.status, "container_statuses", None) or [])
        ):
            state = status.state
            if state and state.waiting:
                container_state = "waiting"
                reason = state.waiting.reason
                exit_code = None
            elif state and state.running:
                container_state = "running"
                reason = None
                exit_code = None
            elif state and state.terminated:
                container_state = "terminated"
                reason = state.terminated.reason
                exit_code = state.terminated.exit_code
            else:
                container_state = "unknown"
                reason = None
                exit_code = None
            if is_abnormal_container(container_state, reason, exit_code):
                return True
        return False

    def list_namespaces(self) -> dict:
        namespaces = self.core.list_namespace(_request_timeout=self.settings.k8s_request_timeout).items
        results: list[dict] = []
        executed_at = now_iso()

        for namespace in namespaces:
            namespace_name = namespace.metadata.name
            pods = self.core.list_namespaced_pod(
                namespace=namespace_name,
                _request_timeout=self.settings.k8s_request_timeout,
            ).items
            abnormal_pod_count = sum(1 for pod in pods if self._is_abnormal_pod(pod))
            results.append(
                {
                    "name": namespace_name,
                    "status": "warning" if abnormal_pod_count > 0 else "healthy",
                    "pod_count": len(pods),
                    "abnormal_pod_count": abnormal_pod_count,
                    "last_inspected_at": executed_at,
                    "labels": namespace.metadata.labels or {},
                    "abnormal_categories": ["pod_status"] if abnormal_pod_count > 0 else [],
                }
            )

        return {
            "executed_at": executed_at,
            "namespaces": results,
        }

    def list_namespace_labels(self, namespace: str) -> dict:
        try:
            pods = self.core.list_namespaced_pod(
                namespace=namespace,
                _request_timeout=self.settings.k8s_request_timeout,
            ).items
        except ApiException as exc:
            reason = exc.reason or str(exc)
            raise RuntimeError(f"无法读取名称空间 {namespace} 的 Pod 标签：{reason}") from exc

        label_counts: dict[tuple[str, str], int] = {}
        for pod in pods:
            for key, value in (pod.metadata.labels or {}).items():
                label_counts[(key, value)] = label_counts.get((key, value), 0) + 1

        labels = [
            {
                "key": key,
                "values": [value],
                "selector": f"{key}={value}",
                "pod_count": pod_count,
            }
            for (key, value), pod_count in sorted(label_counts.items())
        ]
        return {
            "namespace": namespace,
            "executed_at": now_iso(),
            "labels": labels,
        }

    def list_namespace_pods(
        self,
        namespace: str,
        label_selector: str | None = None,
    ) -> dict:
        try:
            pods = self.core.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
                _request_timeout=self.settings.k8s_request_timeout,
            ).items
        except ApiException as exc:
            reason = exc.reason or str(exc)
            raise RuntimeError(
                f"无法读取名称空间 {namespace} 的 Pod 名单：{reason}"
            ) from exc
        summaries = [
            {
                "name": pod.metadata.name,
                "labels": dict(pod.metadata.labels or {}),
            }
            for pod in pods
        ]
        return {
            "namespace": namespace,
            "label_selector": label_selector,
            "executed_at": now_iso(),
            "pod_count": len(summaries),
            "pods": summaries,
        }

    def _pod_issue_summary(self, pod: client.V1Pod, include_logs: bool = True) -> tuple[str, str | None]:
        phase = pod.status.phase or "Unknown"
        container_statuses = pod.status.container_statuses or []
        waiting_reason = None

        for status in container_statuses:
            if status.state and status.state.waiting and status.state.waiting.reason:
                waiting_reason = status.state.waiting.reason
                break

        describe_summary = f"Pod phase={phase}; node={pod.spec.node_name or 'unknown'}"
        log_summary = None

        if container_statuses:
            restart_total = sum(item.restart_count or 0 for item in container_statuses)
            describe_summary += f"; restarts={restart_total}"

        if waiting_reason:
            describe_summary += f"; waiting_reason={waiting_reason}"

        if include_logs:
            container_logs = self._pod_container_log_summaries(pod)
            log_summary = self._combine_container_log_summaries(container_logs)

        return describe_summary, log_summary

    def _pod_container_log_summaries(self, pod: client.V1Pod) -> dict[str, str]:
        container_logs: dict[str, str] = {}
        for container in pod.spec.containers if pod.spec and pod.spec.containers else []:
            container_name = container.name
            try:
                log_summary = self.core.read_namespaced_pod_log(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    container=container_name,
                    tail_lines=_setting_int(self.settings, "k8s_log_tail_lines", 1000),
                    _request_timeout=self.settings.k8s_request_timeout,
                )
            except ApiException:
                continue
            if log_summary:
                container_logs[container_name] = self._summarize_log_text(
                    log_summary
                )
        return container_logs

    def _combine_container_log_summaries(self, container_logs: dict[str, str]) -> str | None:
        if not container_logs:
            return None
        return "\n".join(
            f"[{container_name}]\n{self._summarize_log_text(log_summary)}"
            for container_name, log_summary in container_logs.items()
        )

    def _summarize_log_text(self, log_text: str | bytes) -> str:
        summary_lines = _setting_int(self.settings, "k8s_log_summary_lines", 5)
        return "\n".join(self._coerce_log_text(log_text).splitlines()[:summary_lines])

    def _coerce_log_text(self, log_text: str | bytes) -> str:
        if isinstance(log_text, bytes):
            return log_text.decode("utf-8", errors="replace")
        if isinstance(log_text, str) and log_text.strip().startswith(("b'", 'b"')):
            try:
                parsed = ast.literal_eval(log_text)
            except (SyntaxError, ValueError):
                return log_text
            if isinstance(parsed, bytes):
                return parsed.decode("utf-8", errors="replace")
        return str(log_text)

    def _bounded_log_sample(
        self,
        log_text: str | bytes,
        allowed_bytes: int,
    ) -> tuple[str, int, bool]:
        encoded = self._coerce_log_text(log_text).encode("utf-8")
        accepted = encoded[: max(0, allowed_bytes)]
        return (
            accepted.decode("utf-8", errors="ignore"),
            len(accepted),
            len(encoded) > len(accepted),
        )

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
        previous_samples: dict[str, str] = {}
        collected_total = 0
        log_pods_read = 0
        truncated = False

        for pod_name in unique_names:
            if collected_total >= limits.max_total_log_bytes:
                truncated = True
                break
            try:
                pod = self.core.read_namespaced_pod(
                    name=pod_name,
                    namespace=namespace,
                    _request_timeout=self.settings.k8s_request_timeout,
                )
            except ApiException:
                continue

            per_pod_bytes = 0
            read_any = False
            samples: dict[str, str] = {}
            containers = list(pod.spec.containers if pod.spec else [])
            for container in containers:
                allowed = min(
                    limits.max_log_bytes_per_pod - per_pod_bytes,
                    limits.max_total_log_bytes - collected_total,
                )
                if allowed <= 0:
                    truncated = True
                    break
                try:
                    raw_log = self.core.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        container=container.name,
                        tail_lines=limits.max_container_log_lines,
                        _request_timeout=self.settings.k8s_request_timeout,
                    )
                except ApiException:
                    continue
                sample, accepted, sample_truncated = self._bounded_log_sample(
                    raw_log,
                    allowed,
                )
                raw_log = ""
                if sample:
                    samples[container.name] = sample
                per_pod_bytes += accepted
                collected_total += accepted
                read_any = True
                truncated = truncated or sample_truncated

            restart_total = sum(
                status.restart_count or 0
                for status in (pod.status.container_statuses or [])
            )
            if restart_total > 0 and containers:
                allowed = min(
                    limits.max_log_bytes_per_pod - per_pod_bytes,
                    limits.max_total_log_bytes - collected_total,
                )
                if allowed > 0:
                    try:
                        raw_previous = self.core.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=namespace,
                            container=containers[0].name,
                            previous=True,
                            tail_lines=limits.max_container_log_lines,
                            _request_timeout=self.settings.k8s_request_timeout,
                        )
                    except ApiException:
                        raw_previous = ""
                    if raw_previous:
                        sample, accepted, sample_truncated = self._bounded_log_sample(
                            raw_previous,
                            allowed,
                        )
                        raw_previous = ""
                        if sample:
                            previous_samples[pod_name] = sample
                        per_pod_bytes += accepted
                        collected_total += accepted
                        read_any = True
                        truncated = truncated or sample_truncated
                else:
                    truncated = True

            if samples:
                container_samples[pod_name] = samples
            if read_any:
                log_pods_read += 1

        return TemporaryPodLogCollection(
            container_samples=container_samples,
            previous_samples=previous_samples,
            log_pods_read=log_pods_read,
            collected_log_bytes=collected_total,
            truncated=truncated,
        )

    def _pod_previous_log_summary(self, pod: client.V1Pod) -> str | None:
        container_statuses = pod.status.container_statuses or []
        restart_total = sum(item.restart_count or 0 for item in container_statuses)
        if restart_total <= 0:
            return None

        container_name = pod.spec.containers[0].name if pod.spec and pod.spec.containers else None
        if not container_name:
            return None

        try:
            previous_log = self.core.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                container=container_name,
                previous=True,
                tail_lines=_setting_int(self.settings, "k8s_log_tail_lines", 1000),
                _request_timeout=self.settings.k8s_request_timeout,
            )
        except ApiException:
            return None

        return self._summarize_log_text(previous_log) if previous_log else None

    def _pod_containers(self, pod: client.V1Pod) -> list[dict]:
        result: list[dict] = []
        for status in pod.status.container_statuses or []:
            state = "unknown"
            reason = None
            if status.state:
                if status.state.waiting:
                    state = "waiting"
                    reason = status.state.waiting.reason
                elif status.state.running:
                    state = "running"
                elif status.state.terminated:
                    state = "terminated"
                    reason = status.state.terminated.reason
                    if reason == "Completed" and status.state.terminated.exit_code not in (None, 0):
                        reason = "Error"

            result.append(
                {
                    "name": status.name,
                    "restart_count": status.restart_count or 0,
                    "state": state,
                    "reason": reason,
                }
            )
        return result

    def _related_services(self, pod: client.V1Pod, services: list[client.V1Service]) -> list[dict]:
        pod_labels = pod.metadata.labels or {}
        related: list[dict] = []
        for service in services:
            selector = service.spec.selector or {}
            if selector and all(pod_labels.get(key) == value for key, value in selector.items()):
                related.append({"kind": "Service", "name": service.metadata.name, "status": "healthy"})
        return related

    def _build_pod_result(
        self,
        namespace: str,
        pod: client.V1Pod,
        services: list[client.V1Service],
        *,
        include_logs: bool = False,
        log_collection: TemporaryPodLogCollection | None = None,
    ) -> dict:
        describe_summary, _ = self._pod_issue_summary(pod, include_logs=False)
        if include_logs and log_collection is not None:
            container_log_summaries = {
                container_name: self._summarize_log_text(sample)
                for container_name, sample in log_collection.container_samples.get(
                    pod.metadata.name,
                    {},
                ).items()
            }
        elif include_logs:
            container_log_summaries = self._pod_container_log_summaries(pod)
        else:
            container_log_summaries = {}
        log_summary = self._combine_container_log_summaries(container_log_summaries)
        statuses = pod.status.container_statuses or []
        restarts = sum(item.restart_count or 0 for item in statuses)
        waiting_reason = next(
            (
                item.state.waiting.reason
                for item in statuses
                if item.state and item.state.waiting and item.state.waiting.reason
            ),
            None,
        )
        ready_condition = next(
            (
                condition
                for condition in getattr(pod.status, "conditions", None) or []
                if condition.type == "Ready"
            ),
            None,
        )
        ready = (
            True
            if pod.status.phase == "Succeeded"
            else bool(ready_condition and ready_condition.status == "True")
        )
        return {
            "name": pod.metadata.name,
            "labels": pod.metadata.labels or {},
            "status": (
                waiting_reason
                or ("NotReady" if pod.status.phase == "Running" and not ready else None)
                or pod.status.phase
                or "Unknown"
            ),
            "ready": ready,
            "node_name": pod.spec.node_name,
            "restarts": restarts,
            "containers": self._pod_containers(pod),
            "events": (
                self._pod_events(namespace, pod.metadata.name)
                if include_logs
                else []
            ),
            "describe_summary": describe_summary,
            "log_summary": log_summary,
            "container_log_summaries": container_log_summaries,
            "previous_log_summary": (
                self._summarize_log_text(
                    log_collection.previous_samples[pod.metadata.name]
                )
                if include_logs
                and log_collection is not None
                and pod.metadata.name in log_collection.previous_samples
                else self._pod_previous_log_summary(pod)
                if include_logs and log_collection is None
                else None
            ),
            "resource_usage": {"cpu": "n/a", "memory": "n/a"},
            "related_resources": self._related_services(pod, services),
        }

    def _log_hits_from_pod(self, pod_result: dict) -> list[dict]:
        container_logs = pod_result.get("container_log_summaries") or {}
        if not container_logs:
            return []
        hits: list[dict] = []
        for container_name, log_summary in container_logs.items():
            hits.append({
                "keyword": "log_excerpt",
                "category": "runtime",
                "severity": "warning",
                "source": "current_log",
                "matched_text": log_summary,
                "container_name": container_name,
                "whitelisted": False,
                "whitelist_rule_id": None,
            })
        return hits

    def _evidence_bundle_from_pod(self, namespace: str, pod_result: dict) -> dict:
        return {
            "object_type": "pod",
            "namespace": namespace,
            "name": pod_result["name"],
            "status": pod_result["status"],
            "node_name": pod_result.get("node_name"),
            "restarts": pod_result.get("restarts"),
            "describe_summary": pod_result.get("describe_summary"),
            "events": pod_result.get("events", []),
            "resource_usage": pod_result.get("resource_usage", {}),
            "log_hits": self._log_hits_from_pod(pod_result),
            "related_resources": pod_result.get("related_resources", []),
        }

    def _pod_events(self, namespace: str, pod_name: str) -> list[str]:
        field_selector = f"involvedObject.kind=Pod,involvedObject.name={pod_name}"
        try:
            events = self.core.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector,
                _request_timeout=self.settings.k8s_request_timeout,
            ).items
        except ApiException:
            return []

        result: list[str] = []
        for event in events[-5:]:
            message = event.message or ""
            reason = event.reason or "Unknown"
            result.append(f"{reason}: {message}")
        return result

    def _target_namespaces_for_cluster(self) -> list[str]:
        namespaces = ["kube-system", "ingress-nginx", "calico-system", "calico-apiserver", "gpu-operator", "nvidia-device-plugin"]
        existing = {ns.metadata.name for ns in self.core.list_namespace(_request_timeout=self.settings.k8s_request_timeout).items}
        return [item for item in namespaces if item in existing]

    def _classify_component(self, namespace: str | None, name: str) -> str:
        full_name = f"{namespace or ''}/{name}".lower()

        if "calico" in full_name:
            return "Calico CNI"
        if "ingress-nginx" in full_name or "nginx-ingress" in full_name:
            return "ingress-nginx"
        if "nvidia" in full_name:
            return "NVIDIA device plugin"
        if "ascend" in full_name:
            return "Ascend device plugin"
        if "containerd" in full_name:
            return "containerd"
        if "kubelet" in full_name:
            return "kubelet"
        if namespace == "kube-system":
            return "Kubernetes 控制面初始化状态"
        return "cluster component"

    def get_overview(self) -> dict:
        issues: list[dict] = []
        nodes = self.core.list_node(_request_timeout=self.settings.k8s_request_timeout).items
        ready_nodes = 0

        for node in nodes:
            node_ready = False
            for condition in node.status.conditions or []:
                if condition.type == "Ready" and condition.status == "True":
                    node_ready = True
                    break
            if node_ready:
                ready_nodes += 1
            else:
                issues.append(
                    {
                        "name": node.metadata.name,
                        "component": "Node",
                        "namespace": None,
                        "node": node.metadata.name,
                        "status": "NotReady",
                        "summary": "Node Ready 条件异常",
                    }
                )

        for namespace in self._target_namespaces_for_cluster():
            pods = self.core.list_namespaced_pod(namespace, _request_timeout=self.settings.k8s_request_timeout).items
            for pod in pods:
                describe_summary, _ = self._pod_issue_summary(pod, include_logs=False)
                if self._is_abnormal_pod(pod):
                    phase = pod.status.phase or "Unknown"
                    issues.append(
                        {
                            "name": pod.metadata.name,
                            "component": self._classify_component(namespace, pod.metadata.name),
                            "namespace": namespace,
                            "node": pod.spec.node_name,
                            "status": phase,
                            "summary": describe_summary,
                        }
                    )

        total_nodes = len(nodes) or 1
        health_score = max(0, int((ready_nodes / total_nodes) * 100) - min(len(issues) * 3, 40))
        health_status = "healthy" if not issues else "warning"

        return {
            "health_status": health_status,
            "health_score": health_score,
            "last_checked_at": now_iso(),
            "issues": issues[:20],
            "recent_summary": f"共检查 {len(nodes)} 个节点，发现 {len(issues)} 个异常对象。",
        }

    def run_cluster_inspection(
        self,
        *,
        include_logs: bool = False,
    ) -> dict:
        results: list[dict] = []

        for node in self.core.list_node(_request_timeout=self.settings.k8s_request_timeout).items:
            for condition in node.status.conditions or []:
                if condition.type == "Ready" and condition.status != "True":
                    results.append(
                        {
                            "component": "Node",
                            "namespace": None,
                            "node": node.metadata.name,
                            "status": "NotReady",
                            "describe_summary": condition.message or "Node Ready condition is not True",
                            "log_summary": None,
                        }
                    )

        for namespace in self._target_namespaces_for_cluster():
            pods = self.core.list_namespaced_pod(namespace, _request_timeout=self.settings.k8s_request_timeout).items
            for pod in pods:
                if self._is_abnormal_pod(pod):
                    phase = pod.status.phase or "Unknown"
                    describe_summary, log_summary = self._pod_issue_summary(
                        pod,
                        include_logs=include_logs,
                    )
                    results.append(
                        {
                            "component": self._classify_component(namespace, pod.metadata.name),
                            "namespace": namespace,
                            "node": pod.spec.node_name,
                            "status": phase,
                            "describe_summary": describe_summary,
                            "log_summary": log_summary,
                        }
                    )

        return {
            "health_status": "healthy" if not results else "warning",
            "executed_at": now_iso(),
            "results": results,
        }

    def run_namespace_inspection(
        self,
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = False,
        limits: CollectionLimits | None = None,
    ) -> dict:
        pods = self.core.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        services = self.core.list_namespaced_service(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        ingresses = self.networking.list_namespaced_ingress(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        daemonsets = self.apps.list_namespaced_daemon_set(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        endpoint_slices = self.discovery.list_namespaced_endpoint_slice(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items

        resource_collector = self._get_resource_collector()
        resource_collector._now = datetime.now(timezone.utc)
        if label_selector:
            related = resource_collector._filter_collections_for_target_pods(
                {
                    "pods": pods,
                    "services": services,
                    "deployments": [],
                    "statefulsets": [],
                    "daemonsets": daemonsets,
                    "replicasets": [],
                    "jobs": [],
                    "cronjobs": [],
                    "ingresses": ingresses,
                    "slices": endpoint_slices,
                    "pvcs": [],
                }
            )
            services = related["services"]
            ingresses = related["ingresses"]
            daemonsets = related["daemonsets"]
            endpoint_slices = related["slices"]

        log_collection = (
            self.collect_pod_log_samples(
                namespace,
                [pod.metadata.name for pod in pods],
                limits or CollectionLimits(),
            )
            if include_logs
            else None
        )
        pod_results = (
            [
                self._build_pod_result(
                    namespace,
                    pod,
                    services,
                    include_logs=True,
                    log_collection=log_collection,
                )
                for pod in pods
            ]
            if include_logs
            else [
                self._build_pod_result(namespace, pod, services)
                for pod in pods
            ]
        )

        service_observations = resource_collector._service_observations(
            services,
            pods,
            endpoint_slices,
            ingress_service_names=resource_collector._ingress_service_names(ingresses),
        )
        service_results = [
            {
                "name": observation.resource.name,
                "status": (
                    "skipped"
                    if str(observation.facts.get("service_type")).casefold() == "externalname"
                    else "healthy"
                    if int(observation.facts.get("ready_endpoints") or 0) > 0
                    else "warning"
                ),
                "summary": (
                    f"type={observation.facts.get('service_type')}; "
                    f"ready_endpoints={observation.facts.get('ready_endpoints', 0)}"
                ),
            }
            for observation in service_observations
        ]
        try:
            ingress_classes = {
                item.metadata.name
                for item in self.networking.list_ingress_class(
                    _request_timeout=self.settings.k8s_request_timeout,
                ).items
            }
        except ApiException:
            ingress_classes = set()
        ingress_observations = resource_collector._ingress_observations(
            ingresses,
            services,
            service_observations,
            ingress_classes,
        )
        ingress_results = [
            {
                "name": observation.resource.name,
                "status": (
                    "warning"
                    if observation.facts.get("missing_backend_services")
                    or observation.facts.get("invalid_backend_ports")
                    or observation.facts.get("services_without_ready_endpoints")
                    or observation.facts.get("missing_ingress_class")
                    else "skipped"
                    if int(observation.facts.get("service_backends") or 0) == 0
                    and int(observation.facts.get("resource_backends") or 0) > 0
                    else "healthy"
                ),
                "summary": "仅验证 Ingress 配置链路，不代表集群外访问正常",
            }
            for observation in ingress_observations
        ]
        daemonset_results = [
            {
                "name": daemonset.metadata.name,
                "status": "healthy" if daemonset.status.number_unavailable in (None, 0) else "degraded",
                "summary": f"desired={daemonset.status.desired_number_scheduled}, unavailable={daemonset.status.number_unavailable or 0}",
            }
            for daemonset in daemonsets
        ]
        tls_collection = ProviderCollectionResult(layer="status")
        tls_observations = resource_collector._tls_observations(
            ingresses,
            tls_collection,
        )
        secret_results = [
            {
                "name": observation.resource.name,
                "status": (
                    "critical"
                    if observation.facts.get("exists") is False
                    or observation.facts.get("parse_ok") is False
                    or observation.facts.get("key_match") is False
                    or observation.facts.get("host_match") is False
                    or float(observation.facts.get("days_until_expiry") or 0) <= 7
                    else "warning"
                    if float(observation.facts.get("days_until_expiry") or 0) <= 30
                    else "healthy"
                ),
                "summary": "已检查证书有效期、SAN 和密钥匹配",
            }
            for observation in tls_observations
        ]

        health_status = (
            "warning"
            if any(is_abnormal_pod(item) for item in pod_results)
            or any(item["status"] not in {"healthy"} for item in [
                *service_results,
                *ingress_results,
                *daemonset_results,
                *secret_results,
            ])
            else "healthy"
        )

        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": health_status,
            "executed_at": now_iso(),
            "evidence_bundles": [self._evidence_bundle_from_pod(namespace, pod) for pod in pod_results],
            "pods": pod_results,
            "services": service_results,
            "ingresses": ingress_results,
            "tls_secrets": secret_results,
            "daemonsets": daemonset_results,
        }

    def run_pod_inspection(self, namespace: str, pod_name: str) -> dict:
        try:
            pod_obj = self.core.read_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                _request_timeout=self.settings.k8s_request_timeout,
            )
        except ApiException as exc:
            if exc.status == 404:
                raise LookupError(f"pod {namespace}/{pod_name} not found") from exc
            raise
        services = self.core.list_namespaced_service(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        pod = self._build_pod_result(
            namespace,
            pod_obj,
            services,
            include_logs=True,
        )

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
            "evidence_bundle": self._evidence_bundle_from_pod(namespace, pod),
        }

    def _pods_for_scope(self, pods: list[dict], scope: str | None) -> list[dict]:
        if not scope or "/" not in scope:
            return pods

        scope_kind, scope_name = scope.split("/", 1)
        if scope_kind == "pod":
            return [pod for pod in pods if pod.get("name") == scope_name]

        workload_prefix = f"{scope_name}-"
        return [pod for pod in pods if pod.get("name") == scope_name or str(pod.get("name", "")).startswith(workload_prefix)]

    def collect_diagnosis_context(self, namespace: str, scope: str | None) -> dict:
        inspection = self.run_namespace_inspection(namespace, None)
        return {
            "namespace": namespace,
            "scope": scope,
            "pods": self._pods_for_scope(inspection["pods"], scope),
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }

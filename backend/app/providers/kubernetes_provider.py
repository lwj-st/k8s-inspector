from __future__ import annotations

from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException

from app.core.config import Settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KubernetesInspectionProvider:
    def __init__(self, settings: Settings):
        if not settings.kubeconfig_path:
            raise ValueError("kubeconfig_path is required when provider_mode=kubernetes")

        config.load_kube_config(
            config_file=settings.kubeconfig_path,
            context=settings.kube_context,
        )
        self.settings = settings
        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()
        self.networking = client.NetworkingV1Api()
        self.api_client = ApiClient()

    def _serialize(self, obj: object) -> str:
        return str(self.api_client.sanitize_for_serialization(obj))

    def _pod_issue_summary(self, pod: client.V1Pod) -> tuple[str, str | None]:
        phase = pod.status.phase or "Unknown"
        container_statuses = pod.status.container_statuses or []
        waiting_reason = None

        for status in container_statuses:
            if status.state and status.state.waiting and status.state.waiting.reason:
                waiting_reason = status.state.waiting.reason
                break

        effective_status = waiting_reason or phase
        describe_summary = f"Pod phase={phase}; node={pod.spec.node_name or 'unknown'}"
        log_summary = None

        if container_statuses:
            restart_total = sum(item.restart_count or 0 for item in container_statuses)
            describe_summary += f"; restarts={restart_total}"

        if waiting_reason:
            describe_summary += f"; waiting_reason={waiting_reason}"

        if effective_status in {"CrashLoopBackOff", "Error", "OOMKilled"} or phase != "Running":
            container_name = pod.spec.containers[0].name if pod.spec and pod.spec.containers else None
            if container_name:
                try:
                    log_summary = self.core.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        container=container_name,
                        tail_lines=20,
                        _request_timeout=self.settings.k8s_request_timeout,
                    )
                    log_summary = "\n".join(log_summary.splitlines()[:5])
                except ApiException:
                    log_summary = None

        return describe_summary, log_summary

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

    def _is_non_problem_terminal_pod(self, pod: client.V1Pod) -> bool:
        phase = pod.status.phase or "Unknown"
        owner_kinds = {owner.kind for owner in (pod.metadata.owner_references or []) if owner.kind}
        return phase == "Succeeded" and "Job" in owner_kinds

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
                phase = pod.status.phase or "Unknown"
                describe_summary, _ = self._pod_issue_summary(pod)
                if phase != "Running" and not self._is_non_problem_terminal_pod(pod):
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

    def run_cluster_inspection(self) -> dict:
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
                phase = pod.status.phase or "Unknown"
                if phase != "Running" and not self._is_non_problem_terminal_pod(pod):
                    describe_summary, log_summary = self._pod_issue_summary(pod)
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

    def run_namespace_inspection(self, namespace: str, label_selector: str | None) -> dict:
        pods = self.core.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items
        services = self.core.list_namespaced_service(
            namespace=namespace,
            label_selector=label_selector,
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
        secrets = self.core.list_namespaced_secret(
            namespace=namespace,
            _request_timeout=self.settings.k8s_request_timeout,
        ).items

        pod_results: list[dict] = []
        for pod in pods:
            describe_summary, log_summary = self._pod_issue_summary(pod)
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
            pod_results.append(
                {
                    "name": pod.metadata.name,
                    "status": waiting_reason or pod.status.phase or "Unknown",
                    "restarts": restarts,
                    "events": self._pod_events(namespace, pod.metadata.name),
                    "describe_summary": describe_summary,
                    "log_summary": log_summary,
                    "resource_usage": {"cpu": "n/a", "memory": "n/a"},
                }
            )

        service_results = [
            {
                "name": service.metadata.name,
                "status": "healthy",
                "summary": f"type={service.spec.type or 'ClusterIP'}",
            }
            for service in services
        ]
        ingress_results = [
            {
                "name": ingress.metadata.name,
                "status": "healthy" if ingress.status and ingress.status.load_balancer is not None else "unknown",
                "summary": f"rules={len(ingress.spec.rules or []) if ingress.spec else 0}",
            }
            for ingress in ingresses
        ]
        daemonset_results = [
            {
                "name": daemonset.metadata.name,
                "status": "healthy" if daemonset.status.number_unavailable in (None, 0) else "degraded",
                "summary": f"desired={daemonset.status.desired_number_scheduled}, unavailable={daemonset.status.number_unavailable or 0}",
            }
            for daemonset in daemonsets
        ]
        secret_results = [
            {
                "name": secret.metadata.name,
                "status": "healthy",
                "summary": f"type={secret.type or 'Opaque'}",
            }
            for secret in secrets
            if secret.type and "tls" in secret.type.lower()
        ]

        health_status = "healthy"
        if any(item["status"] not in {"Running", "healthy"} for item in pod_results):
            health_status = "warning"

        return {
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": health_status,
            "executed_at": now_iso(),
            "pods": pod_results,
            "services": service_results,
            "ingresses": ingress_results,
            "tls_secrets": secret_results,
            "daemonsets": daemonset_results,
        }

    def collect_diagnosis_context(self, namespace: str, scope: str | None) -> dict:
        inspection = self.run_namespace_inspection(namespace, None)
        return {
            "namespace": namespace,
            "scope": scope,
            "pods": inspection["pods"],
            "related_objects": {
                "services": inspection["services"],
                "ingresses": inspection["ingresses"],
                "daemonsets": inspection["daemonsets"],
                "tls_secrets": inspection["tls_secrets"],
            },
        }

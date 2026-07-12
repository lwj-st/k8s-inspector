from datetime import datetime, timezone


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

    def run_cluster_inspection(self) -> dict:
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
                    "log_summary": "failed to load default backend",
                }
            ],
        }

    def run_namespace_inspection(self, namespace: str, label_selector: str | None) -> dict:
        pods = [build_demo_pod()]
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
            "health_status": "healthy" if pod["status"] == "Running" else "warning",
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

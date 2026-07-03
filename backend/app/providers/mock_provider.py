from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return {
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": "warning",
            "executed_at": now_iso(),
            "pods": [
                {
                    "name": "demo-api-7c8f6f7c6b-fh2ns",
                    "status": "CrashLoopBackOff",
                    "restarts": 6,
                    "events": ["Back-off restarting failed container"],
                    "describe_summary": "容器启动后健康检查失败并退出。",
                    "log_summary": "database connection refused",
                    "resource_usage": {"cpu": "220m", "memory": "180Mi"},
                }
            ],
            "services": [
                {"name": "demo-api", "status": "healthy", "summary": "ClusterIP 正常"}
            ],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
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
            },
        }

# Namespace 健康状态回修记录

## 证据字段确认

单 namespace 巡检结果已经包含本轮要求的证据字段：

- `pods[].status`
- `pods[].containers[].state`
- `pods[].containers[].reason`
- `pods[].containers[].restart_count`
- `pods[].events`
- `pods[].log_hits`
- `pods[].related_resources`
- `services`、`ingresses`、`daemonsets`、`tls_secrets` 的 `status`

因此没有新增 provider 证据字段，也没有采集完整日志、白名单或模板匹配能力。

## 本次修改

- Kubernetes provider 的 namespace `health_status` 现在同时检查 Pod、Service、Ingress、DaemonSet 和 TLS Secret。
- 任一对象状态不是 `Running` 或 `healthy` 时返回 `warning`。
- 补充 ingress `unknown`、daemonset `degraded` 和全部健康三种 provider 测试。
- 补充 batch summary 关联对象异常时 `summary.status` 与 `health_status` 均为 `warning` 的保护测试。

## 验证

- `python3 -m pytest -q backend/tests`：66 passed
- `cd frontend && npm test -- --run`：31 passed
- `cd frontend && npm run build`：通过

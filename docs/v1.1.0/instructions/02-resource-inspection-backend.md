# Agent 02 指令：v1.1.0 资源巡检后端

## Agent 名称

`v1.1-resource-inspection`

## 开工条件

必须等 `v1.1-contract-architecture` 的契约通过总调度验收。

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/v1.1.0/architecture-contract.md`
- 当前 Kubernetes Provider、Pod 健康判定、巡检服务、Helm RBAC 和相关测试

## 目标

实现 v1.1.0 的真实 Kubernetes 资源采集和健康判定，消除 Service、Ingress、TLS 等资源的假健康。

## 允许修改

- `backend/app/providers/**`
- `backend/app/services/pod_health.py`
- 新增的 `backend/app/services/resource_*` 或契约指定的资源判定模块
- 资源采集和判定相关后端测试
- `deploy/helm/k8s-inspector/templates/clusterrole.yaml`
- `worklog/v1.1-resource-inspection-<实际日期>.md`

开工前必须把实际计划文件逐项写入 worklog。白名单外文件必须先申请总调度批准。

## 禁止修改

- `backend/app/models/**`
- `backend/app/db/**`
- `backend/app/security/**`
- `backend/app/api/router.py`
- `backend/app/api/routes/**`
- `backend/app/main.py`
- `frontend/**`
- Helm Deployment、Secret、ConfigMap 和 values

## 必须完成

1. 工作负载：
   - Deployment
   - StatefulSet
   - DaemonSet
   - Job
   - CronJob
2. Service 和 EndpointSlice。
3. Ingress 到 Service、EndpointSlice、Pod 的关联。
4. Ingress TLS Secret 的证书解析、有效期、SAN 和私钥匹配。
5. PVC、PV、StorageClass 关联和存储事件。
6. Node Ready、Pressure、NetworkUnavailable、taint、allocatable 和 Pod requests 汇总。
7. `metrics.k8s.io` 可选采集与显式 skipped。
8. 基于 `ownerReferences` 建立 workload 与 Pod 关系。
9. 为每个检查返回已冻结的 Issue candidate 和 Coverage 结果。
10. 更新 Mock Provider，使前端和测试能看到正常、异常、跳过、失败。
11. 扩展 Helm 只读 RBAC。
12. 实现分层采集：定时巡检只采集轻量状态，只有异常对象、模板目标或主动日志巡检才读取日志。
13. EndpointSlice 合并同一 Service 的全部 Slice，并按 Kubernetes 语义将 `ready=null` 解释为可用。
14. 静态 Ingress 链路结果使用“配置链路”，不声称真实网络访问成功。
15. 记录 API 调用数、日志读取对象数、字节数和采集耗时。
16. 读取 Kubernetes 服务端版本；1.34 至 1.36 正常支持，低于支持范围时返回明确提示而不是静默继续。
17. 补齐 Pod Ready、init container、last terminated、镜像拉取、探针、Unschedulable、长时间 Terminating 和重启计数证据。
18. 对 Pod 实际引用的 ConfigMap、Secret、ServiceAccount、imagePullSecret 和 PVC 做定点存在性检查；不得批量读取全部 ConfigMap 或 Secret，API 返回后立即丢弃不需要的 data。
19. 将 Secret 和 ConfigMap RBAC 拆分为最小读取权限，禁止写权限。
20. 原始日志只通过契约指定的临时内部对象参与匹配，不得放入可持久化的巡检响应；输出必须带截断标记。
21. Event 按 type、reason、count 和时间规范化；Normal Event 不创建问题，过期 Warning Event 不持续告警。
22. 明确处理期望副本为 0、暂停发布、CronJob suspended、Node cordon、正常 taint、Completed Job/Pod 和未配置 resource limit，避免把合法状态判为故障。
23. StorageClass `WaitForFirstConsumer`、PV `Retain` 和未配置 deadline 的长时间 Job 按 PRD 降级为预期状态或 info，不误判为故障。
24. 检查显式 IngressClass 引用；Resource Backend 标记不适用，不按 Service 缺失处理。
25. 修正 label selector 语义：选择目标 Pod，关联 Service/Ingress/Workload 通过真实对象关系查找，不把 Pod selector 直接传给其他资源列表 API。
26. 集群巡检从实际工作负载发现组件，不依赖固定名称空间列表；可选组件缺失为 skipped，契约配置的必需组件缺失才告警。

## 实现边界

1. 资源判定尽量放入独立服务模块，不继续膨胀单个 Provider 文件。
2. 不实现定时调度、Issue 持久化和通知。
3. 不读取非 TLS Secret 内容。
4. TLS 私钥不得写日志、数据库或 API。
5. 不使用 Pod exec。
6. 不实现主机 containerd/kubelet systemd 检查。
7. 不通过名称猜测未暴露控制面进程健康；可见 Pod 只按工作负载和 Pod 规则判断。
8. 不在没有数据时生成卷使用率。
9. Ingress 不以 loadBalancer 是否为空作为唯一健康依据。
10. 不根据时间接近推断唯一根因。
11. 不对所有正常 Pod 默认读取日志。
12. 不解析、持久化、记录或返回非 TLS Secret 内容；配置依赖检查只保留对象名和存在性。
13. 不把完整容器日志放入 InspectionRecord 或 API DTO。

## 必测场景

覆盖 PRD 第 14 节中资源相关的 1 至 18 项。

每个资源检查至少包含：

- 正常
- 异常
- 不适用/跳过
- API 失败

## 验收命令

至少执行：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_overview_api.py
helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml
```

新增测试文件必须一并执行。

资源 API fixture 至少覆盖 Kubernetes 1.34 和 1.36 的字段兼容。

Pod 和工作负载 fixture 必须覆盖 Running 但 Ready=False、init container 失败、ImagePullBackOff、FailedMount、缺失引用对象、Terminating 超时、Normal Event、过期 Warning Event、期望副本为 0、暂停发布、CronJob suspended、Node cordon 和未配置 limit。

## Worklog

输出：

```text
worklog/v1.1-resource-inspection-<实际日期>.md
```

在 worklog 中单独列出：

- 新增 Kubernetes API 和 RBAC
- 每个 skipped 条件
- 没有可靠数据而明确未实现的检查
- 实际 API 调用和日志采集预算
- 最终 `git diff --name-only` 与允许修改清单对比

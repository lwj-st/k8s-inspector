# 自动巡检切片 7 Review 返工指令

## Review 结论

切片 7 暂不通过，需要小范围返工。

已通过部分：

1. 名称空间批量巡检中，`Succeeded + terminated / Completed` 不再计入异常 Pod。
2. 名称空间证据抽屉中，`safeapi-migrate` 这类已完成 Pod 会进入“正常 / 已完成 Pod”折叠区。
3. 前端 `StatusBadge` 已把 `Succeeded` / `Completed` 显示为正常样式。
4. 自动巡检页和名称空间巡检页已复用前端 `podHealth.ts`。
5. 后端 namespace 路径已复用 `pod_health.py`。

阻断问题：

1. 单 Pod 巡检路径还没有使用统一健康语义。
2. `backend/app/providers/kubernetes_provider.py` 的 `run_pod_inspection()` 仍然使用 `pod["status"] == "Running"` 判断健康状态。
3. 这会导致用户如果直接巡检 `Succeeded + terminated / Completed` 的 Pod，仍然得到 `health_status=warning`。
4. 这和切片 7 文档中“统一后端 Pod/容器健康判定”的要求不一致。

额外残余风险：

1. `get_overview()` 仍通过旧的 `_is_non_problem_terminal_pod()` 判断 `Succeeded` 是否正常，当前只允许 `Succeeded + Job owner`。
2. 如果 overview 扫到非 Job owner 但容器已 `Completed` 的 `Succeeded` Pod，仍可能误报。
3. 本轮可以一起修；如果担心影响范围，至少要补测试说明为什么不修。

## 已执行验收

这些命令已通过，但由于发现路径遗漏，不能作为最终通过：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx src/pages/DiagnosisPage.test.tsx
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端相关测试：35 passed
2. 前端相关测试：35 passed
3. 后端全量：81 passed
4. 前端全量：47 passed
5. 前端 build：通过

## 返工任务一：让 “K8s 采集与证据抽取” agent 处理

### 目标

把单 Pod 巡检和 overview 中的 Pod 健康判断也统一到 `backend/app/services/pod_health.py`。

### 必须修改

重点文件：

1. `backend/app/providers/kubernetes_provider.py`
2. `backend/app/providers/mock_provider.py`
3. `backend/tests/test_kubernetes_provider.py`
4. `backend/tests/test_inspection_api.py`

必须处理：

1. `KubernetesInspectionProvider.run_pod_inspection()` 不能再用 `pod["status"] == "Running"` 判断健康。
2. `MockInspectionProvider.run_pod_inspection()` 也不能继续只认 `Running`。
3. 单 Pod 巡检应复用 `is_abnormal_pod(pod)`，`Succeeded + terminated / Completed` 应返回 `health_status=healthy`。
4. `Failed`、`CrashLoopBackOff`、`ImagePullBackOff`、`terminated / Error`、`Completed + exit_code != 0` 仍应返回 warning。
5. `get_overview()` 如果继续判断 Pod 异常，也应复用统一健康语义，不能继续只靠 `_is_non_problem_terminal_pod()`。

### 测试要求

必须补充：

1. `run_pod_inspection()` 遇到 `Succeeded + terminated / Completed` 返回 `health_status=healthy`。
2. `run_pod_inspection()` 遇到异常状态仍返回 `warning`。
3. 如果修改 `get_overview()`，补一条 `Succeeded + Completed` 不进入 overview issues 的测试。
4. 如果保留 `_is_non_problem_terminal_pod()`，说明它是否还能被使用；能删除就删除，避免旧逻辑继续误导。

### 验收命令

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_overview_api.py
python3 -m pytest -q backend/tests
```

### 禁止事项

1. 不改 API schema。
2. 不新增 Pod 健康字段。
3. 不把所有 terminated 都当正常。
4. 不改前端 UI。

完成后更新或新增 worklog：

```text
worklog/codex-auto-inspection-slice-7-health-semantics-2026-07-17.md
```

## 返工任务二：让 “前端工作台与人性化 UI” agent 处理

前端本轮不需要主动返工，除非后端返工改变了既有响应字段。当前禁止前端为了绕过后端遗漏新增字段或硬编码特殊接口。

如果后端修复后前端测试失败，只做最小调整并跑：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx src/pages/PodInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 最终通过标准

切片 7 重新提交后必须满足：

1. 名称空间批量巡检中 `safeapi-migrate` 不再异常。
2. 名称空间证据抽屉中 `safeapi-migrate` 在正常 / 已完成 Pod 区。
3. 单 Pod 巡检 `safeapi-migrate` 返回 `health_status=healthy`。
4. overview 不应因为 `Succeeded + Completed` 误报。
5. 异常 Pod 仍能被发现。
6. 后端全量、前端全量、前端 build 全部通过。

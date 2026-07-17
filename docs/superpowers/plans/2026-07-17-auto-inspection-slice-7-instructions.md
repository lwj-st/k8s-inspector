# 自动巡检切片 7 开发指令

## 背景

用户在真实开发集群构建镜像后发现误报：

```text
异常 Pod
优先处理
safeapi-migrate
节点：real-144 · 重启：0

Succeeded
容器状态
safeapi-migrate：terminated / Completed
事件摘要
暂无事件

Describe 摘要
Pod phase=Succeeded; node=real-144; restarts=0
```

这个 Pod 应该视为正常。名称空间巡检不能只把 `Running` 视为正常，`Succeeded` / `Completed` 的一次性任务、迁移任务也应归入正常 Pod，不能进入“异常 Pod / 优先处理”。

切片 7 先修健康判定误报，再继续做工作台 UI 优化。

## 总体顺序

1. 先让 “K8s 采集与证据抽取” 修复后端健康判定。
2. 再让 “前端工作台与人性化 UI” 修复前端抽屉分类并做 UI 优化。
3. “统一契约与数据模型” 只做轻量复核，不主动扩字段。

不要并行修改同一批健康判定逻辑。后端健康语义稳定后，前端再对齐展示。

## 第一部分：让 “K8s 采集与证据抽取” agent 处理

### 目标

统一后端 Pod/容器健康判定，修复 `Succeeded + terminated / Completed` 被算作异常的问题。

### 必须修改

重点检查这些文件：

1. `backend/app/providers/kubernetes_provider.py`
2. `backend/app/services/inspection_service.py`
3. `backend/tests/test_kubernetes_provider.py`
4. `backend/tests/test_inspection_api.py`
5. 必要时补 `backend/tests/test_discovery_api.py`

当前已知问题：

1. `inspection_service._is_abnormal_pod_status()` 只把 `running/healthy` 当正常。
2. `_build_namespace_batch_summary()` 直接用 `pod.status not in {"Running", "healthy"}` 统计异常 Pod。
3. `_has_abnormal_container()` 把所有非 `running` 容器都算异常，因此 `terminated / Completed` 被误判。
4. `KubernetesInspectionProvider._is_abnormal_pod()` 只允许 `Succeeded` 且 owner 是 `Job` 的 Pod 作为非问题终态，用户反馈中实际应把 `Succeeded + Completed` 作为正常 Pod。
5. `list_namespaces()` 的 `abnormal_categories` 目前只粗略给 `pod_status`，需要避免 Completed 误报。

### 统一健康语义

后端必须实现同一套语义，不能各函数各写一套判断。

Pod 正常：

1. `status` / phase 为 `Running`。
2. `status` / phase 为 `healthy`。
3. `status` / phase 为 `Succeeded`。
4. 如果 provider 输出 `Completed`，也按正常处理。

容器正常：

1. `state=running` 且无异常 reason。
2. `state=terminated` 且 `reason=Completed`。
3. 如果能拿到 exit code，`terminated.reason=Completed` 且 `exit_code=0` 是正常。

容器异常：

1. `waiting` 且 reason 是 `CrashLoopBackOff`、`ImagePullBackOff`、`ErrImagePull`、`CreateContainerConfigError` 等明确异常。
2. `terminated` 但 reason 不是 `Completed`。
3. `terminated` 且 exit code 非 0。
4. restart count 本身不直接代表异常，但如果已有异常 reason，应保留异常。

注意：

1. `Succeeded/Completed` 正常只解决状态类误报。
2. 如果 Completed Pod 的日志命中了非白名单关键字，仍可以产生 `log_keyword` 异常分类。
3. 如果 Completed Pod 有异常事件，也仍可以产生 `event` 异常分类。
4. 不要因为 `Succeeded` 就跳过日志关键字和事件证据。

### 期望行为

真实案例 `safeapi-migrate` 应变为：

1. 不在“异常 Pod”列表。
2. 出现在正常 Pod 折叠区。
3. 不贡献 `pod_status` 异常分类。
4. 不贡献 `container_status` 异常分类。
5. 如果没有事件、没有非白名单日志关键字，不影响名称空间 health status。

### 测试要求

必须新增或调整测试覆盖：

1. namespace batch summary 中 `Succeeded` Pod 的 `abnormal_pod_count=0`。
2. `Succeeded + terminated / Completed` 不产生 `pod_status` 和 `container_status`。
3. `Failed` Pod 仍然异常。
4. `Running + waiting CrashLoopBackOff` 仍然异常。
5. `terminated / Error` 或非 0 exit code 仍然异常。
6. Kubernetes provider 的 `list_namespaces()` 不把 `Succeeded + Completed` 算异常。
7. namespace inspection detail 中 Completed Pod 仍保留 describe、events、log_hits 字段，不丢证据。

### 验收命令

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py
python3 -m pytest -q backend/tests
```

### 禁止事项

1. 不改前端 UI。
2. 不扩 API 字段。
3. 不引入新的 Pod 状态枚举字段。
4. 不把所有 `terminated` 都当正常，只允许 `Completed` / exit code 0 的成功终态。
5. 不移除日志关键字、事件、相关对象的异常判断。

完成后写 worklog：

```text
worklog/codex-auto-inspection-slice-7-health-semantics-2026-07-17.md
```

## 第二部分：让 “前端工作台与人性化 UI” agent 处理

### 前置条件

必须等 “K8s 采集与证据抽取” 的后端健康判定完成并通过测试后再改前端分类。

### 目标

1. 前端证据抽屉与后端健康语义对齐。
2. `Succeeded + terminated / Completed` 显示为正常 Pod。
3. 自动巡检页继续向工作台体验优化，减少长页面和误导性文案。

### 必须修改

重点检查这些文件：

1. `frontend/src/pages/AutoInspectionPage.tsx`
2. `frontend/src/pages/AutoInspectionPage.test.tsx`
3. `frontend/src/pages/NamespaceInspectionPage.tsx`
4. `frontend/src/pages/NamespaceInspectionPage.test.tsx`
5. `frontend/src/styles.css`

当前已知问题：

1. `AutoInspectionPage.isHealthyPod()` 只认 `Running/healthy + container.running`。
2. `NamespaceInspectionPage` 也只用 `isHealthyStatus(pod.status)` 分类。
3. 证据抽屉把 Completed migration Pod 放入“异常 Pod / 优先处理”，这会严重误导用户。
4. 页面仍偏长，按钮和区域层级需要继续整理。

### 统一前端展示语义

前端应定义统一判断函数，不要两个页面各写一套不一致逻辑。

Pod 正常：

1. `Running`
2. `healthy`
3. `Succeeded`
4. `Completed`

容器正常：

1. `running` 且无异常 reason。
2. `terminated / Completed`。

显示要求：

1. `Succeeded` Pod 不显示在“异常 Pod”。
2. `terminated / Completed` 容器不触发异常样式。
3. 正常 Pod 折叠区标题建议使用“正常 / 已完成 Pod”，避免用户以为只有 Running 才正常。
4. `StatusBadge` 可以继续显示 `Succeeded`，但样式不能像错误状态。
5. 如果 Pod 状态正常但有日志关键字命中，仍应突出日志命中，不能因为状态正常就隐藏证据。

### UI 工作台优化范围

在不改后端契约的前提下，继续处理用户已经反馈过的问题：

1. 自动巡检页主操作区更紧凑。
2. “巡检全部”“巡检选中”“运行模板匹配”“查看证据”的主次关系更明确。
3. 批量摘要卡片不要显得像一堆大按钮。
4. 抽屉内部按“结论 -> 证据 -> 操作”组织。
5. 标题文案更像运维工具，不要出现难懂或低价值标题。
6. 导入导出类入口不要占主页面空间；如果页面仍有类似入口，应收进次级区域或弹窗。

### 测试要求

必须新增或调整前端测试：

1. AutoInspectionPage：`Succeeded + terminated / Completed` Pod 出现在正常折叠区，不出现在异常 Pod 区。
2. AutoInspectionPage：`CrashLoopBackOff` Pod 仍在异常区。
3. NamespaceInspectionPage：`Succeeded` 不计入异常 Pod。
4. 如果 Completed Pod 有非白名单日志命中，日志命中仍显示。
5. 模板匹配抽屉入口不能被 UI 调整移除。

### 验收命令

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

### 禁止事项

1. 不改 API 契约。
2. 不改 matcher 语义。
3. 不新增后端字段。
4. 不把证据抽屉改回长页面。
5. 不删除白名单忽略入口。
6. 不删除模板匹配入口。

完成后写 worklog：

```text
worklog/codex-auto-inspection-slice-7-frontend-workbench-2026-07-17.md
```

## 第三部分：让 “统一契约与数据模型” agent 轻量复核

### 目标

确认切片 7 没有不必要地扩 API 契约，且前后端健康语义没有字段层面的分裂。

### 复核范围

1. `backend/app/schemas/common.py`
2. `backend/app/schemas/inspection.py`
3. `frontend/src/api/types.ts`
4. 本文件

### 复核要求

1. 不主动新增字段。
2. 如果前端为了展示新增本地 helper，不应要求后端新增字段。
3. 如果后端状态字符串仍沿用 Kubernetes phase，不应把 `Succeeded` 改名成别的字段值。
4. 确认 `AbnormalCategory` 不新增。

### 验收命令

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx
```

完成后写 worklog：

```text
worklog/codex-auto-inspection-slice-7-contract-review-2026-07-17.md
```

## 总体验收标准

切片 7 完成后，必须满足：

1. 真实集群中的 `safeapi-migrate` 这类 `Succeeded + terminated / Completed` Pod 不再显示为异常。
2. 名称空间异常数量不再被 Completed Pod 撑高。
3. `CrashLoopBackOff`、`Failed`、`ImagePullBackOff` 等异常仍能被发现。
4. 日志关键字、事件、关联对象异常不被健康状态修复误伤。
5. 自动巡检页更像工作台：主操作清楚、证据有层次、模板匹配入口保留。
6. 所有相关测试和 build 通过。

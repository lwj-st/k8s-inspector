# 自动巡检切片二前端接入指令

## 1. 后端验收结论

“巡检编排与检查入口”已完成批量名称空间巡检后端接口，可以交给前端接入。

已验证接口：

- `POST /api/v1/inspections/namespaces/run`

已验证能力：

1. 支持显式传入多个 namespace。
2. 支持 `all_namespaces=true`。
3. `results` 按 namespace name 排序。
4. 单个 namespace 巡检失败不影响整个批量接口。
5. 失败 namespace 返回 `health_status=error` 和 `summary.status=error`。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py backend/tests/test_kubernetes_provider.py backend/tests/test_contract_models.py
python3 -m pytest -q backend/tests
```

结果：

- 定向后端测试：30 passed。
- 后端全量测试：59 passed。

## 2. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 参考：

- `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`
- `docs/superpowers/plans/2026-07-13-auto-inspection-slice-1-acceptance-and-slice-2-instructions.md`
- 本文档

只做切片二前端接入：启用“巡检选中 / 巡检全部”，并展示批量巡检摘要。

## 3. 必做事项

### 3.1 启用自动巡检页按钮

在 `frontend/src/pages/AutoInspectionPage.tsx` 中：

1. 有选中 namespace 时启用“巡检选中”。
2. namespace 列表非空时启用“巡检全部”。
3. 接口执行中按钮进入 loading/disabled 状态，避免重复点击。

### 3.2 调用批量巡检接口

使用现有 client：

- `runNamespaceBatchInspection(payload)`

调用规则：

1. 巡检选中：
   - `runNamespaceBatchInspection({ namespaces: selectedNamespaces, all_namespaces: false })`
2. 巡检全部：
   - `runNamespaceBatchInspection({ namespaces: [], all_namespaces: true })`

### 3.3 展示批量结果摘要

结果区展示每个 namespace：

- namespace name
- `health_status`
- `summary.pod_count`
- `summary.abnormal_pod_count`
- `summary.abnormal_categories`

展示规则：

1. 异常和 error 排在视觉上更醒目。
2. 正常结果可以弱化，但不要隐藏。
3. `health_status=error` 时显示“该名称空间巡检失败”，但不影响其它结果。
4. 结果列表使用摘要卡片或紧凑表格，不要做成长页面堆叠。

### 3.4 错误处理

1. 整个批量接口失败时，显示全局错误和重试入口。
2. 单个 namespace 失败时，按后端返回的 result 展示局部错误。
3. 不要前端自行把局部失败改成全局失败。

## 4. 禁止事项

本切片禁止做：

1. Pod 详情抽屉。
2. 日志详情展示。
3. describe/event 展示。
4. 白名单忽略。
5. 故障模板匹配。
6. 名称空间巡检导入导出。
7. 保存巡检对象。
8. 前端伪造后端不存在的批量结果结构。

## 5. 前端验收标准

必须补测试覆盖：

1. 巡检选中调用 `POST /api/v1/inspections/namespaces/run`，请求体为选中 namespaces。
2. 巡检全部调用 `all_namespaces=true`。
3. 批量结果正常展示。
4. 单个 namespace `health_status=error` 时只显示局部失败。
5. 整个接口失败时显示全局错误。
6. 执行中按钮禁用，避免重复点击。

必须执行：

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

如果前端修改影响 API 类型或 client，也需要执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
```

## 6. 完成后 worklog 要写清楚

worklog 必须说明：

1. 用户现在如何巡检选中 namespace。
2. 用户现在如何巡检全部 namespace。
3. 局部失败如何展示。
4. 哪些能力刻意没做。
5. 跑了哪些测试。


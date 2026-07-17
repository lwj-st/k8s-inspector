# 自动巡检切片一开发指令：自动发现名称空间

## 1. 本轮验收结论

上一轮“统一契约与数据模型”已完成自动巡检第一批契约：

- `AbnormalCategory`
- `NamespaceSummary`
- `NamespaceDiscoveryResponse`
- `NamespaceBatchInspectionRequest`
- `NamespaceBatchInspectionResponse`
- 前端 `discoverNamespaces()`
- 前端 `runNamespaceBatchInspection()`

验证结果：

- `python3 -m pytest -q backend/tests/test_contract_models.py`：11 passed。
- `python3 -m pytest -q backend/tests`：50 passed。
- `cd frontend && npm test -- --run`：20 passed。
- `cd frontend && npm run build`：通过。

本轮没有发现阻塞问题。下一步只做切片一：自动发现名称空间。

## 2. 切片一目标

用户进入系统后，不需要手动输入 namespace，就能看到当前集群全部名称空间列表。

本切片不做：

- 批量巡检执行。
- 日志采集。
- 模板匹配。
- 名称空间巡检导入导出。
- Pod 详情抽屉。
- 大规模 UI 重构。

完成后用户应能做到：

1. 打开自动巡检页面。
2. 看到集群内名称空间列表。
3. 搜索名称空间。
4. 勾选一个或多个名称空间。
5. 看见每个名称空间的轻量摘要。

## 3. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 参考：

- `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`
- `docs/superpowers/plans/2026-07-11-api-contract.md`
- 本文档

只实现 provider 层名称空间发现能力。

必须完成：

1. 在 provider 抽象中增加名称空间发现方法。
   - 建议方法名：`list_namespaces()`。
   - 返回值应能组装成 `NamespaceSummary`。

2. Kubernetes provider 实现：
   - 使用 Kubernetes API list namespace。
   - 读取 namespace name。
   - 读取 labels。
   - 不依赖用户手动输入 namespace。

3. Mock provider 实现：
   - 返回至少 3 个 namespace。
   - 至少包含一个有异常摘要的 namespace。
   - 用于前端和后端测试稳定运行。

4. 轻量摘要规则：
   - `pod_count` 可以通过 list pods 统计，若当前实现成本过高可先返回 0，但必须在 worklog 说明。
   - `abnormal_pod_count` 本切片可以先返回 0 或 mock 值。
   - `status` 至少支持 `unknown`、`healthy`、`warning`。
   - `last_inspected_at` 本切片可为 `null`。
   - `abnormal_categories` 本切片可为空，mock 中可给一个示例。

禁止事项：

- 不采集日志。
- 不做批量巡检。
- 不做模板匹配。
- 不改前端页面。
- 不把 `SavedInspectionTarget` 拉回主流程。

验收标准：

- provider 单元测试覆盖 Kubernetes 和 mock 的名称空间发现。
- 不破坏现有 provider 测试。
- 留下 worklog，说明哪些字段本切片是轻量占位。

## 4. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 在“K8s 采集与证据抽取”完成 provider 方法后开工。

必须完成：

1. 新增发现接口：
   - `GET /api/v1/discovery/namespaces`
   - 返回 `NamespaceDiscoveryResponse`。

2. 新增 route 文件或复用现有 router：
   - 推荐新增 `backend/app/api/routes/discovery.py`。
   - 在总 router 中注册。

3. 新增 service：
   - 推荐 `backend/app/services/discovery_service.py`。
   - service 只负责调用 provider 并组装契约响应。

4. 响应规则：
   - `executed_at` 使用服务端当前时间。
   - `namespaces` 按名称排序。
   - 不能返回完整 Pod 详情。
   - 不能要求请求体。

禁止事项：

- 不实现 `POST /api/v1/inspections/namespaces/run`。
- 不做批量巡检。
- 不做 UI。
- 不加入导入导出。

验收标准：

- API 测试覆盖成功返回。
- API 测试覆盖空 namespace 列表。
- 后端全量测试通过。
- 留下 worklog。

## 5. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 等 `GET /api/v1/discovery/namespaces` 后端接口完成后开工。

必须完成：

1. 新建或改造自动巡检页面。
   - 主入口名称使用“自动巡检”。
   - 进入页面自动调用 `discoverNamespaces()`。

2. 页面首屏必须包含：
   - 名称空间搜索框。
   - 名称空间列表。
   - 多选 checkbox。
   - 已选数量。
   - “巡检选中”和“巡检全部”按钮可以先置灰并标注“下一切片开放”。

3. 列表字段：
   - 名称空间名称。
   - 状态。
   - Pod 数。
   - 异常 Pod 数。
   - 最近巡检时间。

4. 空状态：
   - 没有名称空间时显示明确提示。
   - 接口失败时显示失败原因和重试按钮。

禁止事项：

- 不要手动输入 namespace 作为主路径。
- 不要展示导入导出 textarea。
- 不要展示保存巡检对象。
- 不要做 Pod 详情抽屉。
- 不要 mock 后端不存在的批量巡检结果。

验收标准：

- 前端测试覆盖加载成功、空列表、失败重试、搜索、多选。
- 页面首屏不出现导入导出。
- 前端全量测试和构建通过。
- 留下 worklog。

## 6. 并行与串行关系

执行顺序：

1. “K8s 采集与证据抽取”先做 provider 方法。
2. “巡检编排与检查入口”在 provider 方法完成后做 API。
3. “前端工作台与人性化 UI”在 API 完成后做页面。

本切片不建议并行做前端正式联调，因为接口未实现前容易继续走 mock 或手动输入旧流程。

可以并行的只有：

- “前端工作台与人性化 UI”可以提前做静态草图，但不得合入依赖假数据的主流程。


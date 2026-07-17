# 自动巡检切片一验收结论与切片二开发指令

## 1. 切片一验收结论

切片一“自动发现名称空间”已通过验收，可以进入切片二。

已确认完成：

1. provider 层支持 `list_namespaces()`。
2. mock provider 返回至少 3 个 namespace，包含 `warning` 和 `healthy` 状态。
3. Kubernetes provider 可从 Kubernetes API 自动发现 namespace，并统计 Pod 数和异常 Pod 数。
4. 新增 discovery service，API route 不再直接拼业务。
5. `GET /api/v1/discovery/namespaces` 返回结果按 namespace name 排序。
6. 自动巡检页作为首页，进入后自动加载 namespace 列表。
7. 自动巡检页支持搜索、多选、空状态、失败重试。
8. 自动巡检页没有导入导出 textarea，没有保存巡检对象主流程。

验证命令与结果：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_discovery_api.py
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

- provider/discovery 相关测试：8 passed。
- 后端全量测试：55 passed。
- 前端全量测试：24 passed。
- 前端生产构建：通过。

## 2. 轻微交付问题

`worklog/codex-provider-list-namespaces-2026-07-12.md` 中仍写着 mock provider 当前只提供一个 `demo` namespace，这与当前代码不一致。后续如整理 worklog，可补充说明 mock provider 已回修为多个 namespace。

该问题不阻塞切片二开发。

## 3. 切片二目标

切片二只做“选中名称空间并触发巡检”。

用户应能：

1. 在自动巡检页勾选一个或多个 namespace。
2. 点击“巡检选中”。
3. 点击“巡检全部”。
4. 看到每个 namespace 的执行状态：等待、巡检中、成功、失败。
5. 看到每个 namespace 的基础结果摘要：状态、Pod 数、异常 Pod 数。

切片二不做：

- Pod 详情抽屉。
- 日志详情展示。
- 白名单忽略。
- 故障模板匹配。
- 导入导出。
- 保存巡检对象。

## 4. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 参考：

- `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`
- `docs/superpowers/plans/2026-07-12-auto-inspection-slice-1-instructions.md`
- `docs/superpowers/plans/2026-07-13-auto-inspection-slice-1-acceptance-and-slice-2-instructions.md`

只实现批量名称空间巡检入口。

必须完成：

1. 新增接口：
   - `POST /api/v1/inspections/namespaces/run`
   - 请求体使用 `NamespaceBatchInspectionRequest`。
   - 响应体使用 `NamespaceBatchInspectionResponse`。

2. 支持两种模式：
   - `all_namespaces=true`：自动发现当前全部 namespace 后逐个巡检。
   - `all_namespaces=false`：只巡检请求体里的 `namespaces`。

3. 编排规则：
   - 复用现有单 namespace 巡检能力。
   - 每个 namespace 独立执行，单个失败不应导致整个批量请求失败。
   - 单个失败时，该 namespace 返回 `health_status=error` 或等价状态，并在 summary 中体现。
   - `requested_namespaces` 必须记录用户请求。
   - `results` 按 namespace name 排序。

4. 响应内容：
   - 每个 result 至少包含 `summary`、`health_status`、`detail_target`。
   - 本切片不要内联完整 Pod 详情。
   - `summary.pod_count` 和 `summary.abnormal_pod_count` 可以来自巡检结果。
   - `summary.abnormal_categories` 至少能在异常 Pod 时包含 `pod_status`。

禁止事项：

- 不做前端页面。
- 不做 Pod 详情抽屉。
- 不做模板匹配。
- 不引入保存巡检对象。
- 不把导入导出放进巡检流程。

验收标准：

- API 测试覆盖巡检选中多个 namespace。
- API 测试覆盖 `all_namespaces=true`。
- API 测试覆盖单个 namespace 失败不影响其它 namespace。
- 后端全量测试通过。
- 留下 worklog。

## 5. 给“K8s 采集与证据抽取”的指令

切片二原则上不需要“K8s 采集与证据抽取”先开工。

只有当“巡检编排与检查入口”发现现有 provider 的单 namespace 巡检结果无法生成 `NamespaceBatchInspectionResponse.summary` 时，才让“K8s 采集与证据抽取”补最小字段。

允许补：

- 从现有 `run_namespace_inspection()` 结果中稳定提供 Pod 数。
- 从现有 `run_namespace_inspection()` 结果中稳定提供异常 Pod 数。

禁止补：

- 日志详情。
- Pod 详情抽屉所需结构。
- 模板匹配。

## 6. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 等 `POST /api/v1/inspections/namespaces/run` 后端接口完成后再开工。

必须完成：

1. 自动巡检页启用按钮：
   - 有选中 namespace 时启用“巡检选中”。
   - 始终允许“巡检全部”，除非 namespace 列表为空。

2. 调用接口：
   - “巡检选中”调用 `runNamespaceBatchInspection({ namespaces: selected, all_namespaces: false })`。
   - “巡检全部”调用 `runNamespaceBatchInspection({ namespaces: [], all_namespaces: true })`。

3. 展示执行状态：
   - 按 namespace 展示巡检中、成功、失败。
   - 执行中按钮要有 loading 状态，避免重复点击。

4. 展示批量摘要：
   - namespace。
   - health_status。
   - pod_count。
   - abnormal_pod_count。
   - abnormal_categories。

5. 交互边界：
   - 本切片不打开 Pod 详情。
   - 点击异常 namespace 可以先提示“详情下一切片开放”。
   - 不要出现导入导出。
   - 不要出现保存巡检对象。

验收标准：

- 前端测试覆盖巡检选中。
- 前端测试覆盖巡检全部。
- 前端测试覆盖接口失败。
- 前端测试覆盖按钮 loading 和禁用状态。
- 前端全量测试和 build 通过。
- 留下 worklog。

## 7. 推荐执行顺序

1. 先让“巡检编排与检查入口”完成后端批量巡检接口。
2. 后端通过验收后，再让“前端工作台与人性化 UI”接入按钮和摘要展示。
3. “K8s 采集与证据抽取”只在缺少 summary 字段时补最小能力，不主动扩范围。


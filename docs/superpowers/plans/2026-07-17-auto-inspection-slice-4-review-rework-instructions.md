# 自动巡检切片四 Review 结论与返工指令

## 1. 验收结论

切片四“名称空间巡检结果下钻到 Pod 证据”暂不通过。

已完成部分：

1. 自动巡检批量结果卡片已提供“查看证据”按钮。
2. 点击后会调用 `POST /api/v1/inspections/namespace/run`。
3. 已有右侧证据抽屉或详情面板。
4. 抽屉能展示异常 Pod、正常 Pod 折叠、容器状态、event、describe 摘要、日志关键字命中、Pod 级关联对象。
5. loading、失败、空 Pod 结果已有基础提示。
6. 未发现白名单、模板匹配、完整日志、完整 describe、导入导出、保存巡检对象等越界功能。

阻断问题：

1. 前端点击“查看证据”时没有使用 batch result 的 `detail_target`，而是使用 `summary.name`。
2. 前端二次请求固定传空 `label_selector`，没有按契约透传 `detail_target.label_selector`。
3. 证据抽屉顶部没有展示异常分类，未满足切片四“抽屉顶部展示异常分类”的要求。
4. 证据抽屉没有展示 namespace 级关联对象：`services`、`ingresses`、`daemonsets`、`tls_secrets`。
5. 如果异常来自 Ingress `unknown` 或 DaemonSet `degraded`，而 Pod 都正常，用户点开“查看证据”后仍看不到真正异常原因。
6. 前端测试没有覆盖“使用 `detail_target.namespace` 和 `detail_target.label_selector` 发起详情请求”。
7. 前端测试没有覆盖“namespace 级关联对象异常在抽屉中可见”。

验证结果：

```bash
python3 -m pytest -q backend/tests
# 67 passed, 1 warning

cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
# 13 passed

cd frontend && npm test -- --run
# 33 passed

cd frontend && npm run build
# passed
```

测试通过不代表切片四通过。当前遗漏的是产品链路关键证据展示。

## 2. 给“统一契约与数据模型”的指令

让“统一契约与数据模型” agent 不要新增契约。

当前契约已足够：

1. `NamespaceBatchInspectionResponse.results[].detail_target`
2. `NamespaceInspectionResponse.services`
3. `NamespaceInspectionResponse.ingresses`
4. `NamespaceInspectionResponse.daemonsets`
5. `NamespaceInspectionResponse.tls_secrets`
6. `NamespaceSummary.abnormal_categories`

只需要确认前端必须按文档使用：

1. `detail_target.namespace` 作为详情请求 namespace。
2. `detail_target.label_selector` 如存在必须透传。
3. 不允许用 `summary.name` 替代 `detail_target.namespace`。

除非发现现有类型缺字段，否则不要改 schema、不要改 API。

## 3. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 本轮不主动开发。

后端已满足本切片基础要求：

1. 单 namespace 巡检接口可复用。
2. 返回 `pods`、`evidence_bundles`、`services`、`ingresses`、`daemonsets`、`tls_secrets`。
3. 后端全量测试通过。

只在前端返工后做一次后端回归：

```bash
python3 -m pytest -q backend/tests
```

## 4. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 本轮不主动开发。

当前 provider 已能返回 namespace 级对象状态，前端没有展示才是阻断点。

只在前端返工后做一次 provider 回归：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py
```

## 5. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 返工切片四。

目标文件优先看：

1. `frontend/src/pages/AutoInspectionPage.tsx`
2. `frontend/src/pages/AutoInspectionPage.test.tsx`
3. `frontend/src/features/inspections/useRunNamespaceInspection.ts`
4. `frontend/src/api/client.ts`
5. `frontend/src/api/types.ts`

必须修正：

1. “查看证据”按钮处理函数接收完整 batch result，而不是只接收 `summary`。
2. 二次请求必须使用 `item.detail_target.namespace`。
3. 如果 `item.detail_target.label_selector` 有值，二次请求必须透传；没有值时传 `null`。
4. 证据抽屉顶部必须展示当前 namespace 的异常分类中文标签。
5. 证据抽屉必须展示 namespace 级关联对象摘要：
   - Service
   - Ingress
   - DaemonSet
   - TLS Secret
6. namespace 级对象展示要异常优先：
   - `status !== "healthy"` 的对象优先展示。
   - 全部 healthy 时弱化或折叠展示。
7. 当没有异常 Pod，但存在异常 Ingress/DaemonSet 等关联对象时，抽屉必须明确显示异常原因，不能只显示“正常 Pod”。

禁止事项：

1. 不新增后端接口。
2. 不要求 batch response 内联完整详情。
3. 不展示完整日志原文。
4. 不展示完整 describe 原文。
5. 不新增白名单忽略按钮。
6. 不新增故障模板入口。
7. 不新增导入导出或保存巡检对象。

必须补测试：

1. 点击“查看证据”后，请求体使用 `detail_target.namespace`，而不是 `summary.name`。
2. `detail_target.label_selector` 有值时，详情请求体透传该 label selector。
3. 抽屉顶部展示异常分类中文标签。
4. 只有 namespace 级关联对象异常、Pod 全部正常时，抽屉仍能展示异常对象，例如 `Ingress/demo：unknown` 或 `DaemonSet/agent：degraded`。
5. 正常关联对象弱化或折叠展示。
6. 前端全量测试和 build 通过。

建议验证：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 6. 推荐执行顺序

1. 只让“前端工作台与人性化 UI”先返工。
2. 返工完成后跑前端测试和 build。
3. 再让“巡检编排与检查入口”和“K8s 采集与证据抽取”各自跑后端回归，不做功能改动。

本轮不要并行改同一个前端页面，避免覆盖 UI 细节。


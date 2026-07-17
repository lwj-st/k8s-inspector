# 自动巡检切片三验收结论与切片四开发指令

## 1. 切片三验收结论

切片三“名称空间巡检异常摘要增强”已通过验收，可以进入切片四。

已确认完成：

1. batch summary 从本次巡检结果推导异常分类，不再依赖 discovery 旧摘要。
2. 异常分类覆盖：
   - `pod_status`
   - `container_status`
   - `event`
   - `log_keyword`
   - `related_object`
3. 异常分类输出顺序稳定：
   - `pod_status`
   - `container_status`
   - `event`
   - `log_keyword`
   - `related_object`
4. Kubernetes provider 的 namespace `health_status` 已同时检查 Pod、Service、Ingress、DaemonSet、TLS Secret。
5. 关联对象异常时，`summary.status`、`health_status`、`summary.abnormal_categories` 保持一致。
6. 前端自动巡检页可以展示顶部统计、中文异常分类、error/warning/healthy 排序。

验证命令：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py backend/tests/test_contract_models.py
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端重点测试：37 passed，1 warning。
2. 后端全量测试：66 passed，1 warning。
3. 前端全量测试：31 passed。
4. 前端生产构建：通过。

## 2. 切片四目标

切片四只做“名称空间巡检结果下钻到 Pod 证据”。

用户在自动巡检页完成名称空间批量巡检后，应能从异常 namespace 快速看到：

1. 哪些 Pod 异常。
2. Pod 的状态、重启次数、所在节点。
3. 容器状态和 reason。
4. event 摘要。
5. describe 摘要。
6. 日志关键字命中摘要。
7. 关联对象摘要。

本切片仍然不做：

1. 白名单忽略按钮。
2. 故障模板匹配。
3. 完整日志原文查看。
4. 完整 describe 原文查看。
5. 导入导出。
6. 保存巡检对象。
7. 自动定时巡检。

## 3. 给“统一契约与数据模型”的指令

让“统一契约与数据模型” agent 先检查现有契约是否足够支撑自动巡检页下钻。

优先复用现有结构：

1. `NamespaceBatchInspectionResponse.results[].detail_target`
2. `NamespaceInspectionResponse`
3. `EvidenceBundle`
4. `InspectedPod`
5. `KeywordHit`
6. `RelatedResource`

如现有契约足够，不要新增字段。

只有在前端无法区分下钻入口时，才允许最小补充：

1. 明确 `detail_target` 可作为重新拉取 namespace 详情的参数。
2. 文档中写清楚 batch result 不内联完整详情，详情由二次请求获取。

禁止事项：

1. 不新增大对象到 batch response。
2. 不把完整日志放进契约。
3. 不把完整 describe 放进契约。
4. 不新增白名单或模板字段。

验收标准：

1. 契约文档说明自动巡检页下钻如何获取 namespace 详情。
2. 前后端类型没有冲突。
3. 如果没有代码改动，worklog 中明确写“现有契约足够，无需修改”。

## 4. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 确认现有单 namespace 巡检接口能作为自动巡检下钻详情接口。

目标接口优先复用：

```http
POST /api/v1/inspections/namespace/run
```

必须保证：

1. 接口可以接收 batch result 的 `detail_target.namespace`。
2. 接口返回 `pods`、`evidence_bundles`、`services`、`ingresses`、`daemonsets`、`tls_secrets`。
3. 接口返回的 Pod 已包含 `log_hits`。
4. 接口失败时返回可被前端展示的错误信息。

禁止事项：

1. 不新增新的详情接口，除非现有接口无法复用。
2. 不返回完整日志原文。
3. 不返回完整 describe 原文。
4. 不接入白名单。
5. 不接入模板匹配。

验收标准：

1. 后端测试覆盖自动巡检下钻使用 `detail_target.namespace` 重新拉取详情。
2. 后端测试覆盖详情接口返回 Pod 证据字段。
3. 后端全量测试通过。

## 5. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 只做证据字段稳定性检查。

必须确认单 namespace 巡检结果中每个异常 Pod 至少包含：

1. `name`
2. `status`
3. `node_name`
4. `restarts`
5. `containers[].name`
6. `containers[].state`
7. `containers[].reason`
8. `events`
9. `describe_summary`
10. `log_hits`
11. `related_resources`

如果字段已经存在，不要改 provider。

只有字段缺失时才补最小能力。

禁止事项：

1. 不采集完整日志。
2. 不采集完整 describe。
3. 不做关键字库配置。
4. 不做白名单。
5. 不做模板匹配。

验收标准：

1. provider 测试或 worklog 证明字段稳定。
2. 后端测试通过。

## 6. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 实现自动巡检页的 namespace 结果下钻。

推荐交互：

1. 在 batch 结果卡片上提供“查看证据”按钮。
2. 点击后打开右侧抽屉或页面内详情面板，不跳走长页面。
3. 抽屉顶部展示 namespace、状态、Pod 总数、异常 Pod 数、异常分类。
4. 默认只展开异常 Pod，healthy Pod 折叠或弱化展示。
5. 每个 Pod 卡片展示：
   - 状态
   - 重启次数
   - 节点
   - 容器状态/reason
   - event 摘要
   - describe 摘要
   - 日志关键字命中
   - 关联对象
6. loading、失败、空结果要有明确提示。

UI 要求：

1. 不要把页面继续拉长成大表单。
2. 不要使用巨大按钮。
3. 主页面只保留概览，详情放抽屉或紧凑面板。
4. 文案必须面向排障用户，避免字段名直出。
5. 异常信息优先展示，正常信息弱化。

禁止事项：

1. 不做白名单忽略按钮。
2. 不做模板匹配入口。
3. 不做完整日志原文弹窗。
4. 不做导入导出。
5. 不做保存巡检对象。

验收标准：

1. 前端测试覆盖点击“查看证据”后调用单 namespace 巡检接口。
2. 前端测试覆盖 loading、失败、成功展示。
3. 前端测试覆盖异常 Pod 优先展示。
4. 前端全量测试和 build 通过。

## 7. 推荐执行顺序

1. 先让“统一契约与数据模型”确认是否需要改契约。
2. 再让“巡检编排与检查入口”确认并测试详情接口复用。
3. 同时让“K8s 采集与证据抽取”检查证据字段稳定性。
4. 最后让“前端工作台与人性化 UI”实现抽屉/详情面板。

并行边界：

1. “统一契约与数据模型”只改契约文档和类型，不碰 UI。
2. “巡检编排与检查入口”只改接口编排和后端测试，不碰 provider 采集细节。
3. “K8s 采集与证据抽取”只改 provider 和 provider 测试，不碰前端。
4. “前端工作台与人性化 UI”只在契约稳定后改 UI，不改后端业务逻辑。


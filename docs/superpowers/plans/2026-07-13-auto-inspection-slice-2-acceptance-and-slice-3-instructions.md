# 自动巡检切片二验收结论与切片三开发指令

## 1. 切片二验收结论

切片二“选中名称空间并触发巡检”已通过验收，可以进入切片三。

已确认完成：

1. 自动巡检页支持“巡检选中”。
2. 自动巡检页支持“巡检全部”。
3. 前端调用 `POST /api/v1/inspections/namespaces/run`。
4. 批量巡检结果展示摘要。
5. 单个 namespace 失败只展示局部失败，不升级为全局失败。
6. 整个批量接口失败时展示全局失败。
7. “重试批量巡检”会复用最近一次批量巡检 payload。
8. 未引入 Pod 详情、日志、白名单、模板、导入导出、保存巡检对象等越界能力。

验证命令：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
python3 -m pytest -q backend/tests/test_contract_models.py
```

结果：

- 自动巡检页测试：10 passed。
- 前端全量测试：30 passed。
- 前端生产构建：通过。
- 后端契约测试：11 passed。

## 2. 切片三目标

切片三只做“名称空间巡检异常摘要增强”。

用户应能在批量巡检结果中更快看出：

1. 哪些 namespace 有异常。
2. 异常属于哪类。
3. 有多少异常 Pod。
4. 哪些 namespace 只是局部失败。

本切片仍然不做：

- Pod 详情抽屉。
- describe 详情。
- event 详情。
- 日志详情。
- 白名单忽略。
- 故障模板匹配。
- 导入导出。
- 保存巡检对象。

## 3. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 先确认当前单 namespace 巡检结果是否稳定包含以下信息：

1. Pod 总数。
2. 异常 Pod 数。
3. 异常分类：
   - `pod_status`
   - `container_status`
   - `event`
   - `log_keyword`
   - `related_object`

如果已有字段足够，则不要改 provider。

如果缺字段，只补最小能力：

1. 从现有 Pod 状态和 container state 推导 `pod_status` / `container_status`。
2. 从现有 events 推导 `event`。
3. 从现有 `log_hits` 推导 `log_keyword`。
4. 从关联对象状态推导 `related_object`。

禁止事项：

- 不新增详情结构。
- 不返回完整日志。
- 不实现白名单忽略。
- 不实现模板匹配。

验收标准：

- 后端测试覆盖每类异常分类至少一个样例。
- 正常 namespace 的 `abnormal_categories` 为空。

## 4. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 在需要时调整批量巡检 summary 生成。

必须保证：

1. `NamespaceBatchInspectionResponse.results[].summary.pod_count` 来自本次巡检结果，而不是仅依赖 discovery 旧摘要。
2. `summary.abnormal_pod_count` 来自本次巡检结果。
3. `summary.abnormal_categories` 来自本次巡检结果。
4. `summary.status` 与 `health_status` 一致或可解释。
5. 单个 namespace 失败仍保留 `health_status=error`。

禁止事项：

- 不内联完整 `NamespaceInspectionResponse`。
- 不做前端。
- 不做详情接口。

验收标准：

- API 测试覆盖批量巡检后 summary 使用本次巡检结果。
- API 测试覆盖不同异常分类。
- 后端全量测试通过。

## 5. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 在后端 summary 稳定后开工。

必须完成：

1. 批量摘要结果区按优先级展示：
   - error
   - warning
   - healthy
2. 每个 namespace 卡片展示异常分类的中文标签：
   - `pod_status` -> Pod 状态
   - `container_status` -> 容器状态
   - `event` -> 事件
   - `log_keyword` -> 日志关键字
   - `related_object` -> 关联对象
3. 批量摘要顶部展示：
   - 巡检 namespace 总数。
   - 异常 namespace 数。
   - 失败 namespace 数。
4. 对 healthy 结果继续弱化展示，避免页面太吵。

禁止事项：

- 不做 Pod 详情抽屉。
- 不做日志原文。
- 不做白名单按钮。
- 不做模板匹配入口。
- 不做导入导出。
- 不做保存巡检对象。

验收标准：

- 前端测试覆盖异常分类中文映射。
- 前端测试覆盖 error/warning/healthy 排序。
- 前端测试覆盖顶部统计。
- 前端全量测试和 build 通过。

## 6. 推荐执行顺序

1. 先让“K8s 采集与证据抽取”判断是否需要补异常分类来源。
2. 再让“巡检编排与检查入口”确保 batch summary 使用本次巡检结果。
3. 最后让“前端工作台与人性化 UI”优化摘要展示。


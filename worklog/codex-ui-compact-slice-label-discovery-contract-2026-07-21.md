# Worklog: UI 大调整第一阶段 Label Selector 契约收口

## 时间

- 日期：2026-07-21
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-21-ui-compact-rework-instructions.md` 第一阶段中给“统一契约与数据模型”的任务，只完成 Label Selector 自动发现契约，不做实际采集实现，不改巡检主契约。

## 已完成内容

### 1. 后端新增 Label Selector discovery 契约

已新增：

1. `NamespaceLabelSummary`
2. `NamespaceLabelDiscoveryResponse`

字段固定为：

1. `namespace`
2. `executed_at`
3. `labels[].key`
4. `labels[].values`
5. `labels[].selector`
6. `labels[].pod_count`

### 2. provider / discovery service / route 已补接口签名

已补：

1. `InspectionProvider.list_namespace_labels(namespace)`
2. `discovery_service.discover_namespace_labels(provider, namespace)`
3. `GET /api/v1/discovery/namespaces/{namespace}/labels`

说明：

- 这轮只把契约和入口形状定下来
- 没有实现 Kubernetes 采集逻辑
- 没有在后端替用户选择默认 label

### 3. 前端 type 与 client 已同步

已新增：

1. `NamespaceLabelSummary`
2. `NamespaceLabelDiscoveryResponse`
3. `discoverNamespaceLabels(namespace)`

结论：

- 前端后续可以直接基于该契约做 Label Selector 候选下拉框
- 不需要再用 `any`

### 4. 契约文档已更新

已在 `docs/superpowers/plans/2026-07-11-api-contract.md` 补充：

- `NamespaceLabelDiscoveryResponse`
- `labels` 是候选摘要，不是原始 Pod 列表
- `selector` 是可直接用于巡检的候选值
- 它是“自动发现候选项”，不是强制范围，也不是保存对象

## 刻意没做

- 没有改名称空间巡检结果主契约
- 没有把 Label Selector 存成用户配置
- 没有实现真实采集逻辑
- 没有改 UI

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_discovery_api.py
```

## 当前结论

Label Selector 自动发现契约已经可以作为下一步后端采集实现和前端下拉选择器的稳定边界。前后端类型明确，且没有扩大巡检主契约。

# Worklog: 自动巡检切片四契约复核

## 时间

- 日期：2026-07-14
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-14-auto-inspection-slice-3-acceptance-and-slice-4-instructions.md` 第 3 节，只做自动巡检页下钻 Pod 证据前的轻量契约复核。

## 复核结论

现有契约足够支撑自动巡检页从 batch 结果下钻到 namespace 详情，无需新增字段。

已确认可直接复用：

1. `NamespaceBatchInspectionResponse.results[].detail_target`
2. `NamespaceInspectionResponse`
3. `EvidenceBundle`
4. `InspectedPod`
5. `KeywordHit`
6. `RelatedResource`

原因：

1. batch 结果已经提供 `detail_target`，可以作为详情引用。
2. 单 namespace 巡检结果已经包含 `pods`、`evidence_bundles`、`services`、`ingresses`、`daemonsets`、`tls_secrets`。
3. `InspectedPod` 已包含切片四要求的状态、重启、节点、容器状态、event、describe 摘要、日志命中、关联对象字段。

## 本轮改动

只补了契约文档说明，没有修改 schema、前端类型或 client 字段。

更新内容：

- 在 `docs/superpowers/plans/2026-07-11-api-contract.md` 中明确：
  - `detail_target.namespace` 可直接作为 `POST /api/v1/inspections/namespace/run` 的 `namespace` 参数
  - `detail_target.label_selector` 如存在可透传
  - batch response 不内联完整 namespace 详情，详情通过二次请求获取

## 刻意没做

- 没有新增字段
- 没有修改后端 schema
- 没有修改前端 `types.ts`
- 没有修改前端 `client.ts`
- 没有修改 UI

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端契约测试通过。
2. 前端全量测试通过。
3. 前端生产构建通过。

## 对后续 agent 的边界说明

1. 后端编排层应复用 `POST /api/v1/inspections/namespace/run` 作为下钻详情接口。
2. 前端应通过 `detail_target` 发起二次请求，不要要求 batch response 内联完整详情。
3. 后续切片不要为下钻再扩一套重复详情契约。

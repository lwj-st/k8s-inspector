# Worklog: 自动巡检切片六契约复核

## 时间

- 日期：2026-07-17
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-17-auto-inspection-slice-5-acceptance-and-slice-6-instructions.md` 第 3 节，只复核故障模板手动匹配入口所需契约，不做 matcher 逻辑、不做 UI。

## 复核结论

现有故障模板匹配契约已经足够支撑切片六，后端无需新增诊断字段。

已确认可直接复用：

1. `FaultTemplate`
2. `TemplateTarget`
3. `TemplateCondition`
4. `DiagnosisRequest`
5. `DiagnosisResponse`
6. `matched_conditions`
7. `unmatched_conditions`
8. `evidence_summary`

## 已确认的契约能力

### 1. 模板目标范围

- `TemplateTarget` 已支持 `namespace`
- `TemplateTarget` 已支持 `label_selector`
- 一个模板可包含多个 `targets`
- 兼容输入 `target_groups`

### 2. 条件绑定

- `TemplateCondition.target_ref` 已可把条件绑定到目标组
- `FaultTemplate` 已校验条件引用的 `target_ref` 必须存在

### 3. 诊断结果展示

`DiagnosisResponse` 已可支撑前端展示：

- 命中的模板
- 未命中的模板条件
- matched/unmatched 条件明细
- 证据摘要
- 执行状态

### 4. 多 Pod 语义

当前模板匹配契约已按目标组聚合 Pod 证据，后续 matcher 语义应保持：

- 同一目标范围内匹配多个 Pod 时，任一 Pod 命中即可视为该条件命中

这轮已把该边界补进契约文档。

## 本轮最小收口

虽然后端字段已足够，但前端之前没有共享 `DiagnosisRequest` 类型。

本轮做了最小同步：

1. 在 `frontend/src/api/types.ts` 中新增 `DiagnosisRequest`
2. 在 `frontend/src/api/client.ts` 中让 `runDiagnosis` 直接复用该类型
3. 在契约文档中补清模板匹配输入、输出和边界

## 刻意没做

- 没有新增后端 schema 字段
- 没有改巡检契约
- 没有把完整 namespace 详情塞进诊断响应
- 没有新增 AI 总结字段
- 没有改 matcher 语义实现

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_diagnosis_api.py
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

- 后端契约/诊断测试通过
- 前端测试通过
- 前端 build 通过

## 对后续 agent 的边界说明

1. matcher 和 diagnosis service 后续应继续复用当前 `DiagnosisResponse` 结构。
2. 前端手动模板匹配入口不要再内联诊断请求结构。
3. 如后续要增强展示，优先复用 `template_match_results` 与 `evidence_summary`，不要先扩大对象载荷。

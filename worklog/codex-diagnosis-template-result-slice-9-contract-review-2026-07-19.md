# Worklog: 切片 9 诊断结果契约复核

## 时间

- 日期：2026-07-19
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-19-diagnosis-template-result-slice-9-instructions.md` 的“轻量契约复核”，确认 9A/9B 没有无必要新增 diagnosis response 字段，且前端类型仍覆盖后端输出。

## 检查范围

已检查：

1. `backend/app/schemas/diagnosis.py`
2. `frontend/src/api/types.ts`
3. `backend/app/services/diagnosis_service.py`
4. 切片 9 指令文档

## 复核结论

### 1. 没有无必要新增 response 字段

当前后端 `DiagnosisResponse` 仍只使用既有字段：

1. `status`
2. `namespace`
3. `direction`
4. `scope`
5. `executed_at`
6. `inspection_target`
7. `matches`
8. `template_match_results`
9. `evidence_summary`
10. `llm_supplement`

结论：

- 9A 的结果解释增强是通过充实现有字段内容完成的
- 没有为命中摘要、未命中原因、采集失败模板单独新增 response 字段

### 2. 前端类型仍覆盖后端输出

`frontend/src/api/types.ts` 中的：

1. `DiagnosisRequest`
2. `DiagnosisMatch`
3. `DiagnosisResponse`
4. `TemplateMatchResult`

与后端 `backend/app/schemas/diagnosis.py` 仍保持一致。

重点确认：

- `direction` 仍是 `template_check`
- `template_match_results` 结构未分裂
- `matched_conditions` / `unmatched_conditions` 仍按原结构返回
- `evidence_summary` 仍是摘要数组，没有被替换成大对象详情

### 3. Diagnosis 契约没有被页面展示倒逼扩张

本轮前端展示优化没有要求后端再补：

- “无法判断”专用字段
- 命中数/未命中数字段
- 额外的条件解释字段
- 完整 namespace inspection 结果

结论：

- 契约层仍然保持简洁
- 解释性增强主要体现在 `summary/reason/evidence` 这些现有承载位上

## 刻意没做

- 没有修改后端 schema
- 没有修改前端 diagnosis 类型结构
- 没有新增 response 字段
- 没有修改巡检契约

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_diagnosis_api.py
cd frontend && npm test -- --run src/pages/DiagnosisPage.test.tsx
```

结果：

1. 后端契约/诊断测试：`17 passed, 1 warning`
2. 前端 `DiagnosisPage` 测试：`4 passed`

## 当前结论

切片 9 在契约层没有发生字段膨胀，前后端 diagnosis 类型仍然一致，可继续按当前结构迭代展示体验，不需要新增 API 字段。

# 2026-07-21 日志上下文展示

## 本轮处理

- 核对当前工作树后确认：
  - `KeywordHit` 已具备 `context_before`、`context_after`、`context_text`
  - `PodInspectionPage` 已按 `context_text -> matched_text` fallback 展示日志命中
  - `DiagnosisResultPanel` 已按 `context_text -> matched_text` 展示模板证据中的日志命中
  - `AutoInspectionPage` 证据抽屉也已接入相同展示逻辑
- 本轮未再改动展示实现本身，重点补齐前端测试，防止只是“代码看起来支持”：
  - `PodInspectionPage.test.tsx` 新增 `context_text` 优先展示测试
  - `DiagnosisPage.test.tsx` 新增模板证据上下文展示测试

## 说明

- 展示文案保持为 `命中上下文（不是完整日志）`。
- 本轮不改后端，不改契约，不改白名单逻辑。

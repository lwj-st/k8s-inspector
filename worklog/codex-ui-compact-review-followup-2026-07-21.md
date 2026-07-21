# 2026-07-21 UI 紧凑化返工 follow-up

## 本次完成

1. 按 `docs/superpowers/plans/2026-07-21-ui-compact-rework-review-followup.md` 的“统一契约与数据模型”任务，只补 `KeywordHit` 日志命中上下文契约。
2. 后端 `KeywordHit` 增加兼容字段：
   - `context_before: list[str]`
   - `context_after: list[str]`
   - `context_text: str | None`
3. 前端 `frontend/src/api/types.ts` 同步增加对应可选字段，保持旧响应兼容。
4. 更新 `docs/superpowers/plans/2026-07-11-api-contract.md`，明确：
   - `matched_text` 仍是命中行
   - 上下文来自本次采集到的日志 tail
   - 上下文字段只用于展示，不进入模板匹配语义
5. 在 `backend/tests/test_contract_models.py` 补兼容测试，覆盖：
   - 缺省字段兼容
   - 显式上下文字段可正常校验

## 本次未做

1. 未实现日志上下文抽取逻辑。
2. 未改日志巡检或模板检查 UI 展示。
3. 未调整旧路由或状态巡检入口。

## 协作说明

1. 后续 `K8s 采集与证据抽取` agent 可以直接基于这三个字段产出上下文，不需要再改契约。
2. 后续前端 agent 应优先展示 `context_text`，缺省时回退到 `matched_text`。

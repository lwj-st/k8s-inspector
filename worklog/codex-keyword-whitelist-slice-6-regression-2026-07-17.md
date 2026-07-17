# 2026-07-17 Slice 6 白名单侧回归验证

## 本轮范围

- 只做“关键字库与白名单”侧回归验证。
- 不改白名单 UI。
- 不改关键字管理。
- 不改模板引擎逻辑。

## 确认结果

- 模板匹配不会把 `whitelisted=true` 的日志命中当成有效证据。
  - 现有覆盖：`backend/tests/test_matcher.py::test_match_template_ignores_whitelisted_log_hits`
- 一键忽略后，相关日志条件不会再误匹配模板。
  - 本轮新增覆盖：`backend/tests/test_diagnosis_api.py::test_run_diagnosis_ignore_whitelist_prevents_log_keyword_template_match`

## 本轮新增测试

- 在 `backend/tests/test_diagnosis_api.py` 新增接口级回归：
  1. 先创建只依赖 `log_keyword` 的模板
  2. 再调用 `/api/v1/whitelists/ignore`
  3. 最后运行 `/api/v1/diagnoses/run`
  4. 断言模板结果为未命中，`matches=[]`，`evidence_summary=[]`

## 验证结果

- `python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_whitelist_api.py`
  - 20 passed
- `python3 -m pytest -q backend/tests`
  - 75 passed

## 说明

- 这轮没有新增产品行为，只是把“忽略后不再误匹配模板”补成接口级回归，防止后续切片六开发时回退。

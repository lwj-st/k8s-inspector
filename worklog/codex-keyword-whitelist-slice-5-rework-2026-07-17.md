# 2026-07-17 Slice 5 白名单侧返工记录

## 本轮处理范围

- 只处理“关键字库与白名单”侧验证与补测。
- 不改前端。
- 不改 batch summary 的 `log_keyword` 推导。
- 不改模板匹配。

## 本轮补充

- 在 `backend/tests/test_whitelist_api.py` 补充 `/api/v1/whitelists/ignore` 返回字段断言：
  - `namespace`
  - `label_selector`
  - `pod_name_pattern`
  - `container_name`
  - `keyword`
  - `enabled=true`
  - `note`
- 新增 `test_namespace_inspection_does_not_match_whitelist_when_container_name_differs`
  - 验证 `container_name` 不匹配时不能误命中白名单。
- 新增 `test_namespace_inspection_disabled_whitelist_restores_non_whitelisted_hit`
  - 验证禁用白名单后，下一次巡检命中恢复为 `whitelisted=false`。

## 已有覆盖确认

- `test_ignore_log_hit_creates_whitelist_rule`
  - 已覆盖 `/api/v1/whitelists/ignore` 创建规则。
- `test_namespace_inspection_marks_whitelisted_keyword_hits`
  - 已覆盖下一次 namespace 巡检中命中变为 `whitelisted=true`。
- `test_namespace_inspection_supports_shell_style_pod_name_pattern`
  - 已覆盖 `pod_name_pattern` 为 shell 风格通配符时的匹配。

## 验证结果

- `python3 -m pytest -q backend/tests/test_whitelist_api.py`
  - 11 passed

## 协同阻塞

- `python3 -m pytest -q backend/tests` 当前未全绿。
- 失败点不在白名单服务，而在“巡检编排与检查入口”负责的 batch/详情编排：
  - `backend/tests/test_inspection_api.py::test_run_namespace_batch_inspection_keeps_log_keyword_when_non_whitelisted_hit_exists`
  - `backend/tests/test_inspection_api.py::test_run_namespace_inspection_keeps_whitelisted_log_hits_in_detail_response`
- 当前仓库里的 `backend/app/services/inspection_service.py` 已存在 `_has_effective_log_hit()`，但全量测试结果说明编排链路还有未闭合问题，需要对应 agent 继续处理。

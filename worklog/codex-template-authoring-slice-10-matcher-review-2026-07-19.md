# Worklog: 模板录入页切片 10 matcher 复核

## 时间

- 日期：2026-07-19
- Agent：Codex

## 本次目标

根据 `docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md` 第三步，只做只读复核：

1. 复核前端步骤化录入页保存出来的 `targets` 和 `match_conditions` 是否仍能被现有 matcher 正确消费
2. 复核多 Pod 命中同一对象组时，仍保持“任一 Pod 满足即可”
3. 复核白名单日志命中不会被模板日志条件误判
4. 复核 AND / OR 的 UI 文案与 matcher 语义保持一致

本轮原则上不改代码，除非发现前端 payload 会破坏现有匹配语义。

## 检查范围

已检查：

1. `frontend/src/pages/TemplatesPage.tsx`
2. `frontend/src/pages/TemplatesPage.test.tsx`
3. `frontend/src/features/templates/useTemplates.ts`
4. `frontend/src/api/types.ts`
5. `backend/app/schemas/template.py`
6. `backend/app/engine/matcher.py`
7. `backend/tests/test_matcher.py`
8. `backend/tests/test_diagnosis_api.py`
9. `worklog/codex-template-authoring-slice-10-contract-review-2026-07-19.md`
10. `worklog/codex-template-authoring-slice-10-frontend-2026-07-19.md`

## 复核结论

### 1. 前端保存 payload 仍主用 `targets`

`TemplatesPage.tsx` 的 `buildPayload()` 当前会提交：

1. `targets[]`
   - `target_ref`
   - `namespace`
   - `label_selector`
   - `pod_name_pattern`
   - `resource_scope`
2. `match_conditions[]`
   - `target_ref`
   - `condition_type`
   - `operator`
   - `expected_value`
   - `join_operator`
   - `enabled`
3. `joint_rule.operator`

结论：

- 这与后端 `backend/app/schemas/template.py` 的主输入结构一致
- 没有把 UI 内部草稿结构泄漏成新契约
- 没有回退到 `target_groups/object_scope` 作为主写入结构

### 2. 多 Pod 仍保持“任一 Pod 命中即可”

现有 matcher 语义没有变化：

1. `pod_status`
2. `log_keyword`
3. `event_keyword`
4. `restart_count`

这些条件在 `backend/app/engine/matcher.py` 中都是遍历目标对象组下的 Pod，只要有一个 Pod 满足条件，就会把该条件记为 matched。

前端本轮没有改动以下关键点：

1. `target_ref` 到对象组的绑定关系
2. `pod_name_pattern` 的写入字段名
3. `expected_value` 的基础格式

因此：

- 多 Pod 命中同一对象组时，仍是任一 Pod 满足即可
- 前端步骤化 UI 没有破坏这一语义

### 3. 白名单日志不会被误算为有效证据

`log_keyword` 条件仍由 matcher 消费巡检结果中的 `log_hits`，并且 matcher 中仍有：

1. `if hit.get("whitelisted"): continue`

前端本轮没有改变：

1. `log_keyword` 的 `condition_type`
2. `contains` 的 `operator`
3. `expected_value` 中关键字字符串的格式

因此：

- 白名单日志命中仍不会让模板日志条件误判为有效证据
- 前端 UI 只是改了中文展示文案，没有改日志条件的结构和语义

### 4. AND / OR 文案与 matcher 语义一致

前端条件步骤当前文案：

1. `AND：所有启用条件都满足才命中故障`
2. `OR：任一启用条件满足就命中故障`

matcher 当前语义：

1. `AND`
   - `unmatched_conditions == 0` 才算命中
2. `OR`
   - `matched_conditions > 0` 就算命中

前端保存时：

1. `joint_rule.operator` 使用 `AND / OR`
2. `match_conditions[].join_operator` 也跟随当前 `jointOperator`

结论：

- 当前 UI 文案和 matcher 语义一致
- 没有发现“文案说任一条件，实际上代码要求全部命中”的偏差

### 5. 条件值格式没有破坏 matcher 预期

核对结果：

1. `pod_status + in`
   - 前端提交数组
   - matcher 预期数组
2. `pod_status + equals`
   - 前端提交字符串
   - matcher 预期标量
3. `restart_count`
   - 前端转成数字
   - matcher 使用数值比较
4. `log_keyword / event_keyword`
   - 前端提交字符串
   - matcher 使用 `contains`
5. `related_object_status`
   - 前端提交 `{ resource, statuses[] }`
   - matcher 当前正是按这个结构消费

结论：

- 没有发现会破坏 matcher 的 payload 形状

## 是否需要改代码

本轮结论：不需要。

原因：

1. 前端步骤化重构没有改变模板匹配输入结构
2. 现有 matcher 仍能正确消费前端保存出的模板
3. 没有发现必须做的后端补丁

因此本轮保持只读复核，没有新增业务代码改动。

## 风险提示

虽然这轮没有发现契约或 matcher 语义问题，但仍有两个后续注意点：

1. 前端如果后续继续优化条件编辑器，不要把 `related_object_status.expected_value` 从对象结构改回字符串
2. 前端如果后续引入对象组复制、批量编辑等能力，必须继续保证 `condition.target_ref` 始终指向有效对象组

## 当前结论

切片 10 的前端模板录入页重构没有破坏现有匹配语义，可以继续沿用当前 matcher 和 diagnosis response。

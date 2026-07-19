# Worklog: diagnosis template result slice 9A

## 时间

- 日期：2026-07-19
- Agent：Codex

## 任务范围

根据 `docs/superpowers/plans/2026-07-19-diagnosis-template-result-slice-9-instructions.md`，本轮只处理 9A：

1. 增强 diagnosis / template result 的解释文本
2. 保持现有 response 结构不变
3. 保留采集失败模板，不让整次 diagnosis 失败
4. 保持白名单过滤和多 Pod 任一命中语义不回退

本轮不处理：

1. 前端布局
2. 模板录入页
3. diagnosis response 新字段扩展
4. AI 总结

## 本次已完成内容

### 1. 条件解释文本已统一收口

已在 `backend/app/engine/matcher.py` 增加条件解释函数：

- `describe_condition(condition, matched)`

当前覆盖：

1. `pod_status`
2. `log_keyword`
3. `event_keyword`
4. `restart_count`
5. `related_object_status`

说明：

1. 会带上 `target_ref`
2. 会带上 operator / expected value
3. `log_keyword` 会明确关键字
4. `related_object_status` 会明确资源类型和状态

### 2. diagnosis summary 已从“命中/未命中”变成解释性摘要

已调整 `backend/app/services/diagnosis_service.py`。

当前模板结果摘要规则：

1. 命中模板：
   - 例如：`命中 2/2 个条件：api Pod 状态匹配 CrashLoopBackOff；api 日志命中 connection refused。`
2. 未命中模板：
   - 例如：`未命中：worker 重启次数未达到 >= 3；worker 缺少 services 状态 = degraded。`
3. 采集失败模板：
   - 例如：`无法判断：采集 broken/app=broken 失败，错误：provider failed。`

这样前端不需要再自己猜“为什么命中 / 为什么未命中”。

### 3. 单模板采集失败不再丢模板结果

当前行为：

1. 单个模板采集失败时，`template_match_results` 仍保留该模板
2. `matched=false`
3. `summary` 明确为“无法判断”
4. `reason` 变成对用户更可读的失败说明
5. 整次 diagnosis 继续返回 `200`

### 4. 白名单与多 Pod 语义保持不变

本轮没有改 matcher 的核心判断语义：

1. 白名单日志命中仍不会让模板命中
2. 多 Pod 仍保持“任一 Pod 命中即可”

## 涉及文件

- `backend/app/engine/matcher.py`
- `backend/app/services/diagnosis_service.py`
- `backend/tests/test_matcher.py`
- `backend/tests/test_diagnosis_api.py`

## 测试覆盖

本轮新增/强化覆盖点：

1. 命中模板返回解释性 `summary`
2. 未命中模板返回缺失条件解释
3. 采集失败模板返回“无法判断”摘要
4. 白名单日志不参与模板命中的回归
5. 多 Pod 匹配仍保持任一 Pod 命中即可
6. 条件解释函数覆盖现有五类 condition type

## 验收命令

已执行：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
```

结果：

- `14 passed`

已执行：

```bash
python3 -m pytest -q backend/tests
```

结果：

- `87 passed`

说明：

- 两次测试均只有既有的 `StarletteDeprecationWarning`
- 没有新增失败

## 边界结论

本轮仍保持职责边界清晰：

1. `matcher.py` 负责条件匹配与基础条件解释
2. `diagnosis_service.py` 负责把匹配结果组织成诊断输出摘要
3. 前端不需要也不应该自己拼 diagnosis 语义
4. 没有为这次体验增强新增 response 字段

## 给 9B 的协作说明

后续前端做 9B 时可以直接消费当前已有字段：

1. `summary`
2. `matched_conditions`
3. `unmatched_conditions`
4. `reason`
5. `suggestion`
6. `risk_note`
7. `evidence_refs`

建议：

1. 命中模板优先展示
2. 未命中模板默认折叠
3. `summary` 里包含“无法判断”时单独放到异常提示区

不需要再要求后端新增字段。

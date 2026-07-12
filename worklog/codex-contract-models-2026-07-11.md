# Worklog: 统一契约与数据模型

## 时间

- 日期：2026-07-11
- Agent：Codex

## 本次目标

按总文档要求，优先完成《统一契约与数据模型》收口，冻结共享 schema、前端类型和 API 契约，避免后续任务继续各自扩字段。

## 已完成内容

### 1. 新增 API 契约文档

- 新增：
  - `docs/superpowers/plans/2026-07-11-api-contract.md`

文档中已明确：

- 主字段与兼容字段的边界
- `targets` 与 `target_groups` 的最终策略
- `KeywordHit` 是模板日志条件的统一输入
- `EvidenceBundle` 由 `inspection_service` 最终组装
- 后续任务禁止继续发散共享字段

### 2. 冻结共享枚举

已在 `backend/app/schemas/common.py` 冻结以下枚举：

- `InspectionTargetKind`
  - `namespace`
  - `pod`
  - `template`
- `KeywordHitSeverity`
  - `info`
  - `warning`
  - `error`
  - `critical`
- `TemplateConditionType`
  - `pod_status`
  - `log_keyword`
  - `event_keyword`
  - `restart_count`
  - `related_object_status`
- `TemplateConditionOperator`
  - `equals`
  - `in`
  - `contains`
  - `gte`
  - `lte`
- `TemplateConditionJoinOperator`
  - `AND`
  - `OR`

### 3. 收紧后端 schema

已调整：

- `InspectionTarget.type` 改为枚举
- `KeywordHit.severity` 改为枚举
- `TemplateCondition.condition_type` 改为枚举
- `TemplateCondition.operator` 改为枚举
- `TemplateCondition.join_operator` 改为枚举
- `SavedInspectionTarget.target_type` 收紧为：
  - `namespace`
  - `pod`

### 4. 保留旧字段兼容，但不再作为主字段

当前兼容仍保留：

- `TemplateTarget`
  - `ref` -> `target_ref`
  - `name` -> `pod_name_pattern`
  - `scopes` -> `resource_scope`
- `TemplateCondition`
  - `type` -> `condition_type`
  - `value` -> `expected_value`
- `FaultTemplate`
  - `target_groups` 兼容输入/输出
  - `namespace_scope + label_selector + object_scope` 兼容旧模板输入

结论：

- 旧数据还能读
- 新代码必须主用 `targets`

### 5. 同步前端类型

已同步：

- `frontend/src/api/types.ts`

新增并冻结前端联合类型：

- `InspectionTargetType`
- `KeywordHitSeverity`
- `TemplateConditionType`
- `TemplateConditionOperator`
- `TemplateConditionJoinOperator`

目标是让前端不再用宽松 `string` 承载共享枚举字段。

### 6. 补齐契约测试

已在 `backend/tests/test_contract_models.py` 增加测试：

1. 旧字段兼容测试
- `ref`
- `name`
- `scopes`
- `type`
- `value`

2. 旧模板结构兼容测试
- `target_groups`
- `joint_rule.operator`

3. 非法枚举拒绝测试
- 非法 `severity`
- 非法 `condition_type`
- 非法 `operator`

## 主要涉及文件

### 后端

- `backend/app/schemas/common.py`
- `backend/app/schemas/saved_target.py`
- `backend/tests/test_contract_models.py`

### 前端

- `frontend/src/api/types.ts`

### 文档

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`

## 验证结果

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest -q backend/tests/test_contract_models.py
```

结果：

- `8 passed, 1 warning`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest -q backend/tests
```

结果：

- `35 passed, 1 warning`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `7 files / 11 tests passed`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- build 成功

## 当前结论

《统一契约与数据模型》本轮已完成到可交接状态：

1. 共享字段语义已经冻结
2. 前后端类型已经同步
3. 兼容旧字段的规则已落文档和测试
4. 后续 agent 可以在此基础上并行开发

## 需要其他 agent 协同遵守的事项

### 1. 巡检编排与检查入口

需要遵守：

- 不要自己再扩 `InspectionTarget`
- `EvidenceBundle` 继续由 `inspection_service` 最终组装
- 保存巡检对象如果要扩导入导出或更新，尽量不要再改共享字段

### 2. K8s 采集与证据抽取

需要遵守：

- provider 不要再生成另一套最终 `log_hits` 契约
- provider 输出原始数据即可
- 最终 API 字段仍以 `common.py` 为准

### 3. 关键字库与白名单

需要协同确认：

- `KeywordHit.severity` 现在已经冻结为四档枚举
- 新规则和命中结果不要再返回任意字符串
- 白名单命中的日志，后续模板引擎应默认忽略

### 4. 故障模板与匹配引擎

这是当前最需要同步的一块：

- `log_keyword` 条件后续必须消费 `KeywordHit`
- 不应继续直接扫 `log_summary` 作为最终逻辑
- `joint_rule.operator` 才是当前模板整体 AND/OR 的唯一执行入口
- `join_operator` 当前不要单独再实现一套运行逻辑

### 5. 前端工作台与人性化 UI

需要遵守：

- 页面可展示兼容字段，但新交互应主用 `targets`
- 不要再把共享枚举写成任意 `string`
- 不要在前端自行补一套白名单命中或模板匹配逻辑

## 当前问题与待协商事项

1. `backend/app/engine/matcher.py` 当前仍直接使用 `log_summary`
- 这和契约文档要求不完全一致
- 建议由“故障模板与匹配引擎”任务负责改为消费 `KeywordHit`

2. `backend/app/services/inspection_service.py` 当前会补 `log_hits`
- 这符合本次契约文档的方向
- 但需要和“K8s 采集与证据抽取”任务确认 provider 不再重复造同类最终结构

3. `InspectionRunRequest.target_type` 仍保留 `cluster`
- 这是统一巡检入口的运行类型，不是 `inspection_target.type`
- 后续 agent 不要把这两个概念混用

4. 前端页面当前仍有部分旧兼容字段展示
- 这不算契约问题
- 但后续 UI 收口时应逐步减少对兼容字段的直接依赖

## 交接建议

建议后续顺序：

1. “巡检编排与检查入口”
2. “关键字库与白名单”
3. “故障模板与匹配引擎”
4. “前端工作台与人性化 UI”

如果后续任务需要动共享字段，必须先同步修改：

1. `docs/superpowers/plans/2026-07-11-api-contract.md`
2. 对应后端 schema
3. `frontend/src/api/types.ts`
4. 契约测试

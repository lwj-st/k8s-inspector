# K8s Inspector API 契约冻结说明

本文档用于冻结 2026-07-11 之后的共享契约。

目标：

- 后端 schema 和前端 `frontend/src/api/types.ts` 使用同一套字段
- 后续任务不能各自扩散命名
- 老字段只做兼容，不作为新代码主字段

## 1. 总原则

1. API 主字段统一使用新字段
2. 旧字段只做兼容输入或兼容输出
3. 模板日志条件统一消费 `KeywordHit`
4. `EvidenceBundle` 最终由 `inspection_service` 组装
5. provider 只负责采集原始证据，不负责定义最终 API 契约

## 2. 枚举冻结

### 2.1 InspectionTarget.type

允许值：

- `namespace`
- `pod`
- `template`

说明：

- `cluster` 只用于统一巡检入口 `InspectionRunRequest.target_type`
- 返回给名称空间巡检、Pod 巡检、模板诊断时，`inspection_target.type` 不使用 `cluster`

### 2.2 KeywordHit.severity

允许值：

- `info`
- `warning`
- `error`
- `critical`

### 2.3 TemplateCondition.condition_type

允许值：

- `pod_status`
- `log_keyword`
- `event_keyword`
- `restart_count`
- `related_object_status`

### 2.4 TemplateCondition.operator

允许值：

- `equals`
- `in`
- `contains`
- `gte`
- `lte`

### 2.5 TemplateCondition.join_operator

允许值：

- `AND`
- `OR`

说明：

- 当前真正控制整体逻辑的是模板级 `joint_rule.operator`
- `join_operator` 当前主要用于兼容和展示，不允许另起一套执行语义

## 3. 字段冻结

### 3.1 InspectionTarget

主字段：

- `type`
- `namespace`
- `pod_name`
- `label_selector`
- `saved_target_id`
- `template_id`
- `resource_scope`

### 3.2 KeywordHit

主字段：

- `keyword`
- `category`
- `severity`
- `source`
- `matched_text`
- `container_name`
- `whitelisted`
- `whitelist_rule_id`

规则：

- 模板中的 `log_keyword` 条件必须使用 `KeywordHit`
- 默认只使用 `whitelisted=false` 的命中

### 3.3 EvidenceBundle

主字段：

- `object_type`
- `namespace`
- `name`
- `status`
- `node_name`
- `restarts`
- `describe_summary`
- `events`
- `resource_usage`
- `log_hits`
- `related_resources`

边界：

- provider 输出原始 pod/service/ingress 数据
- `inspection_service` 负责把这些数据整理成 `EvidenceBundle`

### 3.4 TemplateTarget

主字段：

- `target_ref`
- `namespace`
- `label_selector`
- `pod_name_pattern`
- `resource_scope`

兼容输入：

- `ref` -> `target_ref`
- `name` -> `pod_name_pattern`
- `scopes` -> `resource_scope`

说明：

- `TemplateTarget` 自身直接兼容 `ref/name/scopes`。
- `object_scope` 不是 `TemplateTarget` 的直接输入 alias。
- `object_scope` 在 `TemplateTarget` 上是计算输出，等价于 `resource_scope[0]`，当 `resource_scope` 为空时为 `null`。

### 3.5 TemplateCondition

主字段：

- `target_ref`
- `condition_type`
- `operator`
- `expected_value`
- `join_operator`
- `enabled`

兼容输入：

- `type` -> `condition_type`
- `value` -> `expected_value`

### 3.6 FaultTemplate

主字段：

- `targets`
- `match_conditions`
- `joint_rule`

兼容策略：

- 新代码只依赖 `targets`
- `target_groups` 只保留兼容输入和兼容输出
- `namespace_scope + label_selector + object_scope` 只用于兼容旧模板输入
- `target_groups` 兼容输入字段可使用 `ref/name/object_scope`，其中 `object_scope` 会在 `FaultTemplate` 归一化阶段转换为 `targets[].resource_scope`
- `target_groups` 兼容输出字段为 `ref/name/object_scope`，不会输出 `resource_scope`

## 4. 前后端对齐要求

前端类型文件：

- `frontend/src/api/types.ts`

后端共享 schema：

- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/whitelist.py`
- `backend/app/schemas/keyword.py`
- `backend/app/schemas/saved_target.py`

要求：

- 前端联合类型必须覆盖后端枚举
- 后端新增共享字段时，先改本文档，再改 schema，再改前端类型

## 5. 禁止事项

- 不允许新代码继续主用 `target_groups`
- 不允许模板日志条件直接扫描 `log_summary` 作为最终契约
- 不允许 provider 和 service 同时各自定义一套 `log_hits`
- 不允许前端自己补一套白名单命中判断逻辑

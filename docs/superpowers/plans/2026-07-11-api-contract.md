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

### 2.4 AbnormalCategory

允许值：

- `pod_status`
- `container_status`
- `event`
- `log_keyword`
- `related_object`

说明：

- 该枚举用于名称空间自动发现摘要和批量名称空间巡检摘要。
- 这里只表达异常归类，不替代 `KeywordHit`、`EvidenceBundle` 或模板条件语义。

### 2.5 TemplateCondition.operator

允许值：

- `equals`
- `in`
- `contains`
- `gte`
- `lte`

### 2.6 TemplateCondition.join_operator

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
- `context_before`
- `context_after`
- `context_text`
- `container_name`
- `whitelisted`
- `whitelist_rule_id`

规则：

- 模板中的 `log_keyword` 条件必须使用 `KeywordHit`
- 默认只使用 `whitelisted=false` 的命中
- `matched_text` 仍表示命中行本身，不因上下文展示而改变语义。
- `context_before` / `context_after` / `context_text` 为兼容旧接口的可选补充字段；缺省时前端必须允许仅展示 `matched_text`。
- 日志上下文只来自本次采集到的容器日志 tail，不代表完整日志，也不要求服务端返回完整日志。
- 日志上下文字段只用于证据展示，不进入模板条件匹配语义。

### 3.2E WhitelistIgnoreCreate / WhitelistRead

一键忽略主字段：

- `namespace`
- `label_selector`
- `pod_name_pattern`
- `container_name`
- `keyword`
- `note`

白名单读模型主字段：

- `id`
- `namespace`
- `label_selector`
- `pod_name_pattern`
- `container_name`
- `keyword`
- `enabled`
- `note`

说明：

- 自动巡检证据抽屉的一键忽略优先复用现有白名单契约，不新增重复模型。
- 推荐默认忽略范围为 `namespace + pod_name_pattern + container_name + keyword`。
- 如果当前巡检详情来自 `detail_target.label_selector`，一键忽略请求应同时带上该 `label_selector`。
- `pod_name_pattern` 当前默认可直接使用当前 Pod 名，后续如需通配规则编辑，再由 UI 单独扩展。
- `note` 默认可写入来源说明，例如“自动巡检证据抽屉忽略”。
- 创建后返回 `WhitelistRead`，后续是否生效由白名单过滤逻辑决定。

### 3.2A NamespaceSummary

主字段：

- `name`
- `status`
- `pod_count`
- `abnormal_pod_count`
- `last_inspected_at`
- `labels`
- `abnormal_categories`

说明：

- 用于自动发现名称空间列表和批量名称空间巡检摘要。
- `status` 表示名称空间摘要状态，不等价于某一个 Pod 的 phase。
- `abnormal_categories` 只表达该名称空间当前已发现的异常类型集合。

### 3.2B NamespaceDiscoveryResponse

主字段：

- `executed_at`
- `namespaces`

说明：

- 对应自动发现名称空间接口。
- 返回轻量摘要，不内联 Pod 详情。

### 3.2F NamespaceLabelDiscoveryResponse

主字段：

- `namespace`
- `executed_at`
- `labels`

候选项主字段：

- `key`
- `values`
- `selector`
- `pod_count`

说明：

- 对应 `GET /api/v1/discovery/namespaces/{namespace}/labels`。
- `labels` 只返回可用于巡检的 Label Selector 候选摘要，不返回原始 Pod 列表。
- `selector` 是可直接透传给名称空间范围巡检的候选值。
- 该契约表达的是“自动发现候选项”，不是强制巡检范围，也不等于保存对象。

### 3.2C NamespaceBatchInspectionRequest

主字段：

- `namespaces`
- `all_namespaces`

规则：

- `all_namespaces=true` 时允许 `namespaces=[]`。
- `all_namespaces=false` 时必须显式传入至少一个 namespace。
- 该契约用于名称空间批量巡检主流程，不依赖 `SavedInspectionTarget`。

### 3.2D NamespaceBatchInspectionResponse

主字段：

- `executed_at`
- `all_namespaces`
- `requested_namespaces`
- `results`

结果项主字段：

- `summary`
- `health_status`
- `detail_target`

说明：

- `results[].summary` 复用 `NamespaceSummary`。
- `results[].detail_target` 是详情引用目标，供后续进入单名称空间详情或详情抽屉。
- 自动巡检页下钻 namespace 详情时，前端应取 `results[].detail_target.namespace` 作为 `POST /api/v1/inspections/namespace/run` 的 `namespace` 参数。
- 如果 `results[].detail_target.label_selector` 有值，前端在二次请求中可一并透传；没有值时传 `null` 即可。
- 批量结果当前只冻结“摘要 + 详情引用”，不在此层内联完整 `NamespaceInspectionResponse`。
- namespace 详情统一通过二次请求获取，`NamespaceBatchInspectionResponse` 不承担完整详情载荷。

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

模板匹配边界：

- `targets[]` / `target_groups[]` 支持为每个目标单独指定 `namespace` 和 `label_selector`。
- 一个模板可以包含多个 target group，条件通过 `target_ref` 绑定到对应目标。
- 当某个目标范围内匹配到多个 Pod 时，条件语义为“任一 Pod 命中即可”，而不是要求全部 Pod 同时命中。

### 3.7 DiagnosisRequest / DiagnosisResponse

DiagnosisRequest 主字段：

- `namespace`
- `direction`
- `scope`
- `template_id`
- `template_ids`

DiagnosisResponse 主字段：

- `status`
- `inspection_target`
- `namespace`
- `direction`
- `scope`
- `matches`
- `template_match_results`
- `evidence_summary`

DiagnosisMatch 主字段：

- `template_id`
- `template_name`
- `reason`
- `suggestion`
- `command`
- `risk_note`
- `evidence`
- `matched_conditions`
- `unmatched_conditions`

DiagnosisConditionResult 主字段：

- `target_ref`
- `type`
- `operator`
- `value`
- `matched`
- `evidence`

说明：

- 手动模板匹配当前主方向为 `direction=template_check`。
- 诊断服务按模板目标中的 `namespace` 和 `label_selector` 采集证据，不要求用户在检查页重复输入模板范围。
- `matches` 用于前端突出“已命中模板”。
- `template_match_results` 保留每个模板的 matched/unmatched 条件拆解，适合前端展示“为什么命中 / 为什么未命中”。
- `evidence_summary` 只返回匹配证据摘要，不内联完整 namespace 巡检详情。
- 本层不新增 AI 总结字段，现有 `llm_supplement` 仅保留兼容，不作为本切片主契约。

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
- 自动发现名称空间和批量名称空间巡检主流程不得再把 `SavedInspectionTarget` 作为必填前置

## 5. 禁止事项

- 不允许新代码继续主用 `target_groups`
- 不允许模板日志条件直接扫描 `log_summary` 作为最终契约
- 不允许 provider 和 service 同时各自定义一套 `log_hits`
- 不允许前端自己补一套白名单命中判断逻辑

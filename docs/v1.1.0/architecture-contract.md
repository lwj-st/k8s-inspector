# K8s Inspector v1.1.0 架构与契约决策

## 1. 文档状态

- 状态：冻结，等待总调度验收
- 适用版本：v1.1.0
- 契约实现：`backend/app/schemas/v1_1.py`
- 兼容基线：`docs/superpowers/plans/2026-07-11-api-contract.md`

本文件冻结 v1.1.0 的 API 数据结构、数据关系、模块边界和安全约束。后续 Agent 不得复制或另建同义枚举；契约不足时应申请契约返工。

## 2. 核心架构决策

### ADR-01：检查执行状态与对象健康状态分离

对象健康状态固定为：

- `healthy`
- `warning`
- `critical`
- `unknown`

检查执行状态固定为：

- `passed`
- `abnormal`
- `skipped`
- `failed`

`skipped` 表示检查不适用或可选依赖不存在，`failed` 表示本应检查但采集或解析失败。两者都不得转换为 `healthy`。

`Coverage` 是每次检查的执行事实，字段固定为：

- `check_code`
- `name`
- `status`
- `reason`
- `checked_objects`
- `duration_ms`
- `issue_count`

`abnormal/skipped/failed` 必须提供可展示给运维的 `reason`。

### ADR-02：资源判定与问题生命周期分离

资源判定模块输出 `CheckEvaluation`：

```text
CheckEvaluation
├── scope
├── scope_key
├── coverage
└── issue_candidates[]
```

`IssueCandidate` 不包含数据库 ID、fingerprint、首次发现时间、恢复时间和确认信息。它只表达当前一次检查发现的事实。

`scope` 表达 evaluator 本次真实完成检查的范围，不能用 InspectionRun 的请求范围代替。`scope_key` 必须由结构化 scope 确定性生成并通过契约校验；`coverage.issue_count` 必须等于 `issue_candidates` 数量。

Issue 生命周期服务负责：

1. 根据候选问题生成 fingerprint。
2. 新建、续期、重开或恢复 Issue。
3. 写入 IssueEvent。
4. 决定是否创建通知投递任务。

Provider 不创建 Issue，资源判定模块不直接写数据库，通知模块不重新判断资源健康。

### ADR-03：稳定 fingerprint

fingerprint 固定使用 SHA-256，输入只包含：

```json
{
  "cluster_id": "部署配置中的稳定集群标识",
  "source_check": "稳定检查编码",
  "issue_code": "稳定问题编码",
  "resource": {
    "kind": "转为小写后的 Kind",
    "namespace": "集群级对象使用空字符串",
    "name": "对象名称"
  }
}
```

序列化规则为 UTF-8、JSON key 排序、无多余空格。

以下内容禁止进入 fingerprint：

- summary、reason、suggestion 等可变文案
- severity
- 首次或最后发现时间
- Kubernetes UID
- Evidence
- correlation_key
- 手动或定时触发方式

唯一实现入口为 `build_issue_fingerprint()`。各业务模块不得自行拼接字符串计算 fingerprint。`cluster_id` 和 `source_check` 去除首尾空白后不能为空。

### ADR-04：问题恢复规则

一次检查的恢复流程固定为：

1. 检查成功执行并得到 `passed` 或 `abnormal`。
2. 从 `CheckEvaluation.scope` 取得本检查真实覆盖范围。
3. 使用 `build_inspection_scope_key(scope)` 校验本轮 scope_key。
4. 计算本轮该 `source_check + scope_key` 的全部 fingerprint。
5. 校验 `coverage.issue_count == len(issue_candidates)`。
6. 更新本轮命中的 Issue，并激活或刷新该 Issue 对应 scope_key 的内部 membership。
7. 对 `passed/abnormal` 检查，只把同一 `Issue.source_check + membership.scope_key` 下本轮未命中的 active membership 失活。
8. 仅当一个 Issue 已无任何 active membership 时，才把全局 Issue 标记 recovered。

单个 fingerprint 可能被 namespace、pod 等多个 scope 同时发现，因此禁止只在 Issue 表保存单一 scope_key。内部使用 `IssueScopeMembership` 表达多对多覆盖成员关系，至少包含：

- `issue_id`
- `scope_key`
- `active`
- `last_seen_run_id`
- `last_seen_at`
- `deactivated_at`

命中时按 `(issue_id, scope_key)` upsert：设置 `active=true`，刷新 `last_seen_run_id/last_seen_at`，清空 `deactivated_at`。检查为 `passed/abnormal` 且本轮未命中时，只将该 source_check、该 scope_key 的 membership 设置 `active=false` 并记录 `deactivated_at`；`skipped/failed` 不改变 membership。

membership 约束为：`active=true` 时 `deactivated_at` 必须为空；`active=false` 时 `deactivated_at` 必须存在且不得早于 `last_seen_at`。`last_seen_run_id` 必须引用最近一次真正命中该 scope membership 的 Run，不得在未命中或 skipped/failed 时刷新。

若同一 Issue 在其他 scope 仍有 active membership，则不得恢复全局 Issue。这一规则选择保守延迟恢复，避免 namespace 与 pod 等不同 scope 互相误恢复。`IssueScopeMembership` 是内部持久化结构，不向公开 `Issue` DTO 新增字段。

以下情况禁止恢复旧问题：

- Coverage 为 `skipped`
- Coverage 为 `failed`
- 本次执行整体失败
- 对象不在本次实际检查范围内
- 分页、采集上限或局部失败导致对象没有被检查

Issue 再次出现时复用同一 `(cluster_id, fingerprint)` 记录，状态改回 open，并写入 `reopened` 事件。

`recovered_at` 必须大于等于 `last_seen_at`，不得生成时间倒流的生命周期。

手动巡检默认参与生命周期更新，IssueEvent 必须记录 `trigger=manual`。定时巡检记录 `trigger=scheduled`。

确认问题只写：

- `acknowledged_at`
- `acknowledge_note`
- `IssueEvent(event_type=acknowledged)`

确认不得修改 `status`、`recovered_at` 或健康状态。

### ADR-05：correlation_key 只表达确定性关联

允许使用相同 correlation_key 的情况：

- Ingress backend 明确引用 Service
- Service selector 或 EndpointSlice 明确关联 Pod
- Pod volume 明确引用 PVC
- ownerReferences 明确关联工作负载
- 同一故障模板中的明确目标关系

禁止根据发生时间接近、名称相似或经验猜测设置 correlation_key。correlation_key 不参与去重，也不代表唯一根因。

### ADR-06：分层采集

Provider 接口固定使用：

- `ProviderCollectionRequest`
- `ProviderCollectionResult`
- `ProviderObservation`
- `ProviderCollectionFailure`

第一层 `layer=status`：

- 只采集对象状态、轻量字段和真实对象关系。
- `evidence_targets=[]`
- `include_events=false`
- `include_logs=false`

第二层 `layer=evidence`：

- 必须明确给出 `evidence_targets`。
- 只允许为异常对象、模板明确目标或用户主动日志巡检补充证据。
- 是否读取 Event、Log 由 `include_events/include_logs` 明确表达。

每个 `ProviderCollectionRequest` 必须携带本次运行的 `thresholds: InspectionThresholds`。未显式传入时使用既有默认阈值，保持旧调用兼容。运行编排在启动时只读取一次 `InspectionPolicySettings`，形成不可变策略快照，并遵循：

1. 同一运行的 status 请求、evidence 请求和资源 evaluator 使用同一份阈值快照。
2. `warning_event_window_minutes` 决定本次运行的 Warning Event 采集窗口；`pod_restart_window_minutes` 决定本次运行的 Pod 重启增量判定窗口，两者不得在运行中重新读取 Settings。
3. Provider 不得提供或调用 `configure_inspection_policy()` 一类修改共享实例状态的方法，也不得把策略保存到共享可变字段。
4. 并发运行各自携带请求级快照；任一运行的阈值更新不得影响其他运行。

资源 evaluator 接收的策略快照必须与 `ProviderCollectionRequest.thresholds` 来源相同：编排层先得到一个 `policy_snapshot`，把 `policy_snapshot.thresholds` 放入每次采集请求，并把同一 `policy_snapshot` 交给 evaluator。

采集限制由 `CollectionLimits` 传入；定时全局巡检不得隐式读取正常 Pod 日志。

v1.0.0 公共巡检接口与 Provider 内部接口采用不同默认值，避免升级破坏旧客户端，同时保证 v1.1.0 状态层默认轻量：

1. `POST /api/v1/inspections/namespace/run` 的 `include_logs` 可省略，公共请求默认 `true`，保持旧客户端的日志巡检语义；v1.1.0 状态页面必须显式传 `false`。
2. `POST /api/v1/inspections/cluster/run` 的 `include_logs` 查询参数可省略，公共请求默认 `true`；v1.1.0 状态页面必须显式传 `false`。
3. `POST /api/v1/inspections/namespaces/run` 固定为状态采集，必须向 Provider 显式传 `include_logs=false`，不得执行日志数量门禁。
4. Provider 的 namespace 和 cluster 方法内部默认 `include_logs=false`；只有调用方明确开启时才允许读取日志。
5. 日志采集开启时使用本次运行冻结的 `CollectionLimits.max_log_pods`。预检和实际采集之间目标数量发生变化时，仍必须返回统一 422，且不得越过限制继续读取。

单 Pod 下拉候选使用 `GET /api/v1/discovery/namespaces/{namespace}/pods`。该接口只返回 Pod 名称和 labels，可选 `label_selector`，不得创建 InspectionRecord、InspectionRun，不得读取 Event 或 Pod Log。

单个对象采集失败写入 `ProviderCollectionFailure`，由对应检查生成 `failed` Coverage；不得用空数组替代失败。

### ADR-07：证据最小化

持久化证据只使用 `Evidence`：

- 稳定 `code`
- `source`
- 面向人的受限 `summary`
- 结构化 `facts`
- 关联资源引用
- 观测时间
- 截断标记

原始 Pod 日志只允许在内存中匹配，不得进入 DTO、SQLite、通知、API 或日志。`Evidence` 禁止额外字段，并拒绝 raw log、Token、密码、私钥、Cookie、完整 Webhook 地址等敏感 key。

单个 Issue 的全部 Evidence 序列化后不得超过 64 KiB。生产者必须先裁剪、脱敏并设置 `truncated=true`；契约层对超限数据直接拒绝，避免错误落库。

非 TLS Secret 只保存对象引用和“存在/不存在”事实。TLS 私钥内容也不得进入 Evidence。

## 3. 枚举冻结

### 3.1 Issue

- severity：`critical/warning/info`
- status：`open/recovered`
- scope：`cluster/namespace/workload/pod/service/ingress/node/storage`
- event type：`opened/observed/severity_escalated/acknowledged/recovered/reopened`

### 3.2 InspectionRun

- trigger：`manual/scheduled`
- status：`queued/running/succeeded/partial/failed`

`partial` 表示主流程完成，但存在 skipped 或局部 failed 检查；前端不得把它显示为完全成功。

### 3.3 Notification

- channel type：`generic_webhook/feishu_custom_bot`
- event type：
  - `issue_opened`
  - `severity_escalated`
  - `issue_recovered`
  - `inspection_failed`
  - `flapping`
  - `notification_test`
- delivery status：`pending/delivering/succeeded/failed/suppressed`

### 3.4 稳定问题编码

v1.1.0 固定使用 PRD 第 8 节列出的 34 个 `IssueCode`。新增或改名必须经过契约评审，文案变化不得改问题编码。

## 4. Pydantic 契约

### 4.1 Issue 与 IssueEvent

`Issue` 是 API 读模型，包含：

- 持久化身份：`id/cluster_id/fingerprint`
- 问题身份：`issue_code/source_check/scope/resource`
- 当前结论：`severity/status/summary/reason/suggestion/evidence`
- 生命周期：`first_seen_at/last_seen_at/recovered_at/occurrence_count`
- 关联与确认：`correlation_key/acknowledged_at/acknowledge_note`

`ResourceRef` 使用 `api_version/kind/namespace/name/uid`。UID 可作为展示证据，但不参与 fingerprint。

`IssueEvent` 是追加写时间线，不允许更新历史事件。状态或严重程度变化通过 previous/new 字段表达。

### 4.2 InspectionRun

`InspectionRun` 包含：

- `id/plan_id/inspection_record_id`
- `trigger/status/scope`
- `started_at/finished_at/duration_ms`
- `coverage/issue_ids`
- `opened_issue_count/recovered_issue_count`
- `kubernetes_api_calls/log_pods_read/collected_log_bytes`
- 受限的 `error_code/error_message`

失败信息不得包含请求头、Secret、Cookie、Token、完整 Webhook 或原始响应正文。

`InspectionCheckResult` 是 Coverage 的持久化读模型，一条记录对应：

- 一个 `run_id`
- 一个稳定 `check_code`
- 一个明确的 `InspectionScope`
- 与 scope 确定性匹配的 `scope_key`
- Coverage 的 name/status/reason/checked_objects/duration_ms/issue_count
- `completed_at`

InspectionRun 与 InspectionCheckResult 为一对多。同一 Run/check_code 可以按真实 scope 保存多条结果，例如 demo namespace failed、prod namespace passed，不得压成一条而丢失局部失败。

`build_inspection_scope_key()` 使用 scope type、namespace、namespaces、label_selector 和 pod_name 的规范 JSON 计算 SHA-256。namespace 列表先排序，因此输入顺序不影响 key；不同 namespace 必须得到不同 key。InspectionCheckResult 和 CheckEvaluation 都校验 scope_key 与结构化 scope 一致。

`InspectionRun` 是列表和摘要读模型；`InspectionRunDetail` 在其基础上新增 `check_results: InspectionCheckResult[]`，用于 Run 详情返回每个真实范围的执行结果。详情契约校验每条 result.run_id 与 Run id 一致，并拒绝重复的 `(check_code, scope_key)`。

### 4.3 InspectionPlan

计划范围：

- `global`
- `namespaces`，至少一个 namespace

计划间隔：

- `5m`
- `10m`
- `30m`
- `60m`
- `daily`

`daily` 必须提供 `daily_at=HH:MM` 和有效 IANA timezone。固定分钟计划不得提供 `daily_at`。

创建、更新、读取分别使用：

- `InspectionPlanCreate`
- `InspectionPlanUpdate`
- `InspectionPlan`

更新请求至少包含一个字段。通知渠道 ID 必须为正整数且不得重复。

### 4.4 NotificationChannel

创建契约 `NotificationChannelCreate` 接受：

- `name`
- `type`
- `enabled`
- `webhook_url: SecretStr`
- `signing_secret: SecretStr | null`
- `mention_all_on_critical`
- `timeout_seconds`

更新契约 `NotificationChannelUpdate` 不包含 `type`。渠道创建后类型不可变；如需更换类型，应新建渠道并重新绑定计划。更新 Webhook 地址时，服务必须读取持久化的渠道类型并重新执行同类型创建地址规则。

读取契约 `NotificationChannel` 只返回：

- `endpoint_masked`
- `signing_secret_configured`

读取响应没有 `webhook_url`、`signing_secret` 或密文。

`mention_all_on_critical` 只对 `feishu_custom_bot` 有效。统一消息的 `mention_all=true` 只允许 severity=critical。

`feishu_custom_bot` 创建时必须同时满足：

- scheme 为 HTTPS
- host 严格等于 `open.feishu.cn`
- path 为 `/open-apis/bot/v2/hook/{token}`
- 不允许 userinfo、非 443 端口、query 或 fragment

`generic_webhook` 不在渠道 DTO 中强制 HTTPS；开发环境是否允许 HTTP 及生产目标限制统一由 `WebhookTargetPolicy` 和运行环境校验。

飞书范围仅为群自定义机器人 V2 Webhook 单向告警，契约明确禁止额外字段，因此不能加入：

- App ID、App Secret、tenant access token
- 单聊接收人
- 消息接收
- 卡片按钮回调
- 在飞书确认或修复

### 4.5 NotificationMessage 与 Delivery

`NotificationMessage` 是厂商无关的内部消息：

- 集群标识、事件类型
- Issue 或 InspectionRun 身份
- 问题状态和严重程度
- 资源、时间、结论、建议
- 结构化证据摘要
- 使用可信系统配置生成的详情地址
- 测试和截断标记

飞书适配器只负责将该对象转换为非交互式卡片或降级文本，不重新读取 Issue，也不更改健康语义。

`NotificationDelivery` 只保存结构化结果：

- `deduplication_key`
- 渠道、事件和执行引用
- 状态、尝试次数
- HTTP status、厂商 code
- 受限错误 code/message
- 重试与送达时间

禁止保存或返回下游原始响应正文。投递成功必须有 `delivered_at`，最终失败必须有 `error_code`。

连接测试使用 `event_type=notification_test` 和 `is_test=true`，只创建 Delivery，不创建 Issue。

### 4.6 ResourceMetricState

只保存每个资源或容器的最新采样：

- CPU millicores
- memory bytes
- request/limit
- CPU、内存连续超阈值次数
- sampled_at、stale、updated_at

不定义历史 samples 数组，不在 SQLite 中实现时序曲线。

### 4.7 AdminSession 与 SecurityAuditLog

登录请求使用 `AuthLoginRequest`，密码为 `SecretStr`。

`AdminSession` 是公开 Session 响应，只包含：

- `authenticated`
- `username`
- `csrf_token`
- `idle_expires_at`
- `absolute_expires_at`

Session Token 只存在于 HttpOnly Cookie；数据库只存 hash。API 契约没有 token 和 token_hash 字段。

`SecurityAuditLog` 的 details 只能保存简单结构化字段，并拒绝密码、Token、Cookie、私钥、完整 Webhook 等敏感 key。

相同敏感 key 拒绝规则同时应用于公开的 `ApiError.details`、`SystemComponentStatus.details`、`ProviderObservation.facts` 和 `Evidence.facts`，避免错误路径或状态页旁路泄露。

### 4.8 系统状态和健康探针

- `/health/live` 返回 `LiveHealthResponse`，只判断进程存活。
- `/health/ready` 返回 `ReadyHealthResponse`，检查 migration、安全配置和关键初始化。
- `/api/v1/system/status` 返回 `SystemStatus`。

SystemStatus 固定包含：

- 数据库及 schema version
- Kubernetes API
- Provider
- 调度器及最近心跳
- Metrics API
- 通知配置
- 最近巡检
- 配置校验
- 应用版本、cluster_id、Kubernetes 服务端版本及支持状态

Metrics API 或 Webhook 不可用为 degraded，不单独导致进程退出。migration 或生产安全配置缺失导致 not_ready。

### 4.9 必需组件、巡检阈值与运行策略

`RequiredComponentPolicy` 固定字段：

- `name`
- `namespace`
- `kind`
- `label_selector`
- `enabled`

定位规则为 namespace、kind、label selector 三者同时匹配。相同定位规则不得重复；kind 比较不区分大小写。未配置为必需的可选组件不存在时仍为 skipped。

`InspectionPolicySettings` 包含：

- `required_components: RequiredComponentPolicy[]`
- `thresholds: InspectionThresholds`
- `retention: DataRetentionSettings`
- `namespace_concurrency: int`
- `max_log_pods: int`

`InspectionThresholds` 是不可变值对象。Settings 更新通过创建并持久化完整新值完成，已经启动的运行继续使用启动时快照，新阈值只影响之后启动的运行。

`namespace_concurrency` 默认 3，范围 1 至 10。Agent 04 在每次巡检运行启动时从同一份 `policy_snapshot` 读取，并同步写入本轮采集限制；运行过程中不得重新读取 Settings。

`max_log_pods` 默认 200，范围 1 至 1000，只限制会读取多个 Pod 日志的范围巡检和模板日志条件。单 Pod 巡检不受范围数量限制。前端必须读取 Settings 中的当前值；无法读取上限或无法确认范围 Pod 数时，范围日志巡检按安全原则阻断。

`DataRetentionSettings` 默认值固定为：

| 字段 | 默认值（天） | 范围 | 清理对象 |
|---|---:|---:|---|
| `inspection_run_days` | 30 | 7 至 180 | InspectionRun 及可清理关联数据 |
| `recovered_issue_days` | 90 | 7 至 180 | 已恢复且不再活跃的 Issue |
| `notification_delivery_days` | 30 | 7 至 180 | NotificationDelivery |
| `security_audit_days` | 90 | 7 至 180 | SecurityAuditLog |

每日清理任务启动时读取一次完整 `policy_snapshot.retention`，本次任务全程使用该快照；中途设置变更只影响下一次任务。开放 Issue 和仍有 active membership 的 Issue 不参与清理。

默认阈值固定为：

| 字段 | 默认值 | 语义 |
|---|---:|---|
| `tls_warning_days` | 30 | TLS 到期 warning |
| `tls_critical_days` | 7 | TLS 到期 critical |
| `pvc_pending_warning_minutes` | 5 | PVC Pending warning |
| `pvc_pending_critical_minutes` | 30 | PVC Pending critical |
| `pv_released_stale_hours` | 24 | PV Released 清理风险 |
| `job_incomplete_info_minutes` | 60 | 无 deadline Job 的 info 提示 |
| `resource_usage_warning_percent` | 90 | 相对 limit 使用率阈值 |
| `resource_usage_consecutive_cycles` | 3 | 连续定时周期 |
| `pod_terminating_warning_minutes` | 10 | Pod Terminating warning |
| `pod_restart_window_minutes` | 10 | 重启增量窗口 |
| `pod_restart_delta` | 3 | 窗口内重启增量 |
| `warning_event_window_minutes` | 30 | Warning Event 窗口 |
| `node_not_ready_grace_seconds` | 0 | Node NotReady 宽限；0 表示立即 critical |

TLS critical 天数不得大于 warning 天数；PVC warning 分钟不得大于 critical 分钟。`node_not_ready_grace_seconds` 范围为 0 至 3600 秒，默认 0，表示 Ready=False/Unknown 立即 critical。

## 5. v1.0.0 向后兼容

### 5.1 巡检响应

现有以下响应保留全部旧字段和旧语义：

- `ClusterInspectionResponse`
- `NamespaceInspectionResponse`
- `NamespaceBatchInspectionResponse`
- `PodInspectionResponse`

v1.1.0 只追加：

```json
{
  "issues": [],
  "coverage": []
}
```

两个字段类型与 `V11InspectionExtension` 一致，并已直接接入上述四个实际响应模型。两个新增字段必须始终返回数组；没有问题或尚无检查项时返回空数组，不返回 null。传入非空值时响应模型必须原样保留，不得因未声明字段而过滤。

`InspectionRunResponse` 不重复增加顶层 `issues/coverage`；它通过 `cluster_result/namespace_result/pod_result` 嵌套上述响应模型，自然包含对应数组。

禁止删除、重命名或改变下列现有字段：

- `health_status`
- `executed_at`
- `results/pods/services/ingresses/tls_secrets/daemonsets`
- `inspection_target`
- `evidence_bundle/evidence_bundles`

旧客户端可忽略新增字段；新前端不得把字段缺失解释为健康。若与旧服务端兼容，字段缺失应展示“未提供覆盖信息”。

### 5.2 InspectionRecord 与 InspectionRun

`InspectionRecord` 继续服务 v1.0.0 历史接口。v1.1.0 新执行同时创建：

1. 保持旧 API 所需的 InspectionRecord。
2. 新 InspectionRun。
3. InspectionRun 通过可空、唯一的 `inspection_record_id` 关联旧记录。

历史 InspectionRecord 不强制回填 InspectionRun；读取旧记录时不得伪造 Coverage。迁移不得重写或删除旧 result_payload。

### 5.3 模板、关键字和白名单

沿用 2026-07-11 已冻结契约。v1.1.0 不改变：

- `InspectionTarget`
- `KeywordHit`
- `EvidenceBundle`
- `TemplateTarget`
- `TemplateCondition`
- 现有诊断响应

Issue Evidence 是新的受限持久化结构，不得把完整旧 `EvidenceBundle.log_summary` 直接复制进去。

### 5.4 Settings 兼容

现有 `GET/PUT /api/v1/settings` 的旧字段全部保留。v1.1.0 只新增：

```json
{
  "inspection_policy": {
    "required_components": [],
    "namespace_concurrency": 3,
    "retention": {
      "inspection_run_days": 30,
      "recovered_issue_days": 90,
      "notification_delivery_days": 30,
      "security_audit_days": 90
    },
    "thresholds": {
      "...": "使用契约默认值"
    }
  }
}
```

GET 对应契约为 `V11SettingsExtension`。GET 必须始终返回完整 `inspection_policy`；旧数据库没有配置，或旧 JSON 中没有 retention/namespace_concurrency/max_log_pods 时，返回契约默认值。

PUT 的新增部分使用 `V11SettingsUpdateExtension`，其中 `inspection_policy` 是可省略字段：

- 老客户端不传该字段时，保留当前策略；首次升级且无当前策略时使用默认值。
- 传入该字段时整体校验并更新。
- 显式传 null 非法，返回 422；清空必需组件应传完整策略且 `required_components=[]`。
- 不得因旧客户端 PUT 而把必需组件和阈值重置为空或默认值。

本契约不修改现有 `settings.py`；Agent 03 接入时以新增字段扩展现有 SettingsResponse/SettingsUpdate。

## 6. API 冻结

所有接口使用 `/api/v1`，时间统一输出带时区的 ISO 8601。错误响应统一使用 `ApiError(code/message/request_id/details)`，details 不得含敏感信息。

### 6.1 分页

列表统一：

- 请求：`page=1`、`page_size=20`
- `page_size` 最大 100
- 响应：`Page[T]`，固定为 `items/total/page/page_size`

### 6.2 Issue

| 接口 | 请求 | 响应 |
|---|---|---|
| `GET /api/v1/issues` | `IssueListFilter` | `Page[Issue]` |
| `GET /api/v1/issues/{id}` | path id | `Issue`，不存在返回 404 |
| `GET /api/v1/issues/{id}/events` | `PageParams` | `Page[IssueEvent]` |
| `POST /api/v1/issues/{id}/acknowledge` | `IssueAcknowledgeRequest` + CSRF | `Issue` |

筛选字段固定为：

- `status`
- `severity`
- `namespace`
- `resource_kind`
- `source_check`
- `sort`
- `page/page_size`

`sort` 只能使用 `IssueSortMode`，不接受任意字段名或独立排序方向：

| 模式 | 固定服务端排序 |
|---|---|
| `priority` | open 在 recovered 前；severity 按 critical/warning/info；持续时间降序；id 降序 |
| `duration` | open 在 recovered 前；持续时间降序；severity 按 critical/warning/info；id 降序 |
| `last_changed` | 最新 IssueEvent.occurred_at 降序；没有事件时使用 first_seen_at；id 降序 |

默认 `sort=priority`。持续时间在一次查询开始时固定计算：open 使用“查询时间 - first_seen_at”，recovered 使用“recovered_at - first_seen_at”。排序必须在数据库完整筛选结果上完成后再分页，禁止前端或服务端只重排当前页。

问题时间线固定按 `occurred_at` 降序、`id` 降序返回：

- Issue 不存在返回 404。
- `page < 1`、`page_size < 1` 或 `page_size > 100` 返回 422。
- page 超出最后一页时返回 200，`items=[]`，并保留真实 total/page/page_size。
- 前端按需加载更早事件；Issue 详情不得无限内嵌全部 IssueEvent。

### 6.3 InspectionRun

| 接口 | 请求 | 响应 |
|---|---|---|
| `GET /api/v1/inspection-runs` | `InspectionRunListFilter` | `Page[InspectionRun]` |
| `GET /api/v1/inspection-runs/{id}` | path id | `InspectionRunDetail`，包含带 scope/scope_key 的 check_results |

筛选字段固定为 `status/trigger/plan_id/page/page_size`。

### 6.4 InspectionPlan

| 接口 | 请求 | 响应 |
|---|---|---|
| `GET /api/v1/inspection-plans` | `PageParams` | `Page[InspectionPlan]` |
| `POST /api/v1/inspection-plans` | `InspectionPlanCreate` + CSRF | `InspectionPlan`，201 |
| `PUT /api/v1/inspection-plans/{id}` | `InspectionPlanUpdate` + CSRF | `InspectionPlan` |
| `DELETE /api/v1/inspection-plans/{id}` | CSRF | 204 |
| `POST /api/v1/inspection-plans/{id}/run` | CSRF | `InspectionRun`，202 |

手动 run 遇到同计划正在执行时返回 409，不创建第二个并发执行。

### 6.5 NotificationChannel

| 接口 | 请求 | 响应 |
|---|---|---|
| `GET /api/v1/notification-channels` | `PageParams` | `Page[NotificationChannel]` |
| `POST /api/v1/notification-channels` | `NotificationChannelCreate` + CSRF | `NotificationChannel`，201 |
| `PUT /api/v1/notification-channels/{id}` | `NotificationChannelUpdate` + CSRF | `NotificationChannel` |
| `DELETE /api/v1/notification-channels/{id}` | CSRF | 204 |
| `POST /api/v1/notification-channels/{id}/test` | CSRF | `NotificationTestResponse` |

连接测试同步等待单次受限超时；重试可在后台继续，但响应和投递记录必须明确当前状态。

### 6.6 Auth 与系统状态

| 接口 | 访问要求 | 请求/响应 |
|---|---|---|
| `POST /api/v1/auth/login` | 匿名 | `AuthLoginRequest` -> `AdminSession` |
| `POST /api/v1/auth/logout` | 已登录 + CSRF | 204；服务端先撤销 Session 再清 Cookie |
| `GET /api/v1/auth/session` | Cookie 可选 | `AdminSession` |
| `GET /api/v1/system/status` | 已登录 | `SystemStatus` |
| `GET /health/live` | 匿名 | `LiveHealthResponse` |
| `GET /health/ready` | 匿名 | `ReadyHealthResponse` |

登录成功通过 `Set-Cookie` 下发随机 Session Token；响应体不返回 Token。所有受保护写接口使用 `X-CSRF-Token`。

未登录访问受保护 API 返回 401；已登录但缺少或错误 CSRF 返回 403；登录限流返回 429。

### 6.7 Settings

| 接口 | 请求 | 响应 |
|---|---|---|
| `GET /api/v1/settings` | 已登录 | 现有 `SettingsResponse` + `V11SettingsExtension` |
| `PUT /api/v1/settings` | 现有 `SettingsUpdate` + `V11SettingsUpdateExtension` + CSRF | 扩展后的 SettingsResponse |

阈值或必需组件校验失败返回 422 和脱敏 `ApiError`，不得部分保存。

### 6.8 v1.0 巡检兼容与轻量发现

| 接口 | 日志语义 | 说明 |
|---|---|---|
| `POST /api/v1/inspections/cluster/run?include_logs=` | 省略为 `true` | v1.1.0 状态页显式传 `false` |
| `POST /api/v1/inspections/namespace/run` | body 中 `include_logs` 省略为 `true` | 范围日志页显式传 `true`，状态页显式传 `false` |
| `POST /api/v1/inspections/namespaces/run` | 固定 `false` | 批量状态采集，不执行日志上限门禁 |
| `GET /api/v1/discovery/namespaces/{namespace}/pods` | 不读取日志 | query 可传 `label_selector`，只返回轻量 Pod 候选 |

范围日志目标超过当前 `inspection_policy.max_log_pods` 时返回 422：

```json
{
  "code": "INSPECTION_LOG_SCOPE_TOO_LARGE",
  "message": "本次预计读取的 Pod 日志超过上限，请缩小范围",
  "request_id": "request-id",
  "details": {
    "estimated_pods": 201,
    "limit": 200
  }
}
```

超限响应产生前不得读取 Pod Log、创建 InspectionRecord 或创建 InspectionRun。

## 7. Webhook 与飞书安全契约

`WebhookTargetPolicy` 固定：

- 生产环境 HTTPS only
- `follow_redirects=false`，调用方不能改为 true
- 至少配置一个允许 host 或 CIDR
- 阻断 loopback、link-local、private network 和云元数据地址

飞书渠道在创建 DTO 层先执行官方 V2 地址校验；generic webhook 和所有实际出站请求仍必须经过本节目标策略，不能因为 DTO 已校验而跳过 DNS/SSRF 检查。

发送前必须：

1. 解析 URL 并校验 scheme、host、port。
2. 匹配 host/CIDR allowlist。
3. 解析全部 A/AAAA 地址；任何不允许地址都拒绝。
4. 连接时避免 DNS 重绑定绕过，重试前重新完整校验。
5. 禁止自动重定向。
6. 使用受信任配置生成详情页 URL，不读取请求 Host。

飞书转换后 JSON 必须小于等于 30 KB。裁剪顺序为次要 Evidence，其次上下文；必须保留：

- 是否为测试
- 状态与严重程度
- 结论
- 资源
- 时间
- 建议
- 详情链接

签名密钥和 Webhook 地址只以加密字段持久化；运行日志、审计日志和 Delivery 都不得包含明文。

## 8. 数据库实体关系与约束

本节是 Agent 03 的模型和 migration 实现依据，契约阶段不实现 ORM。

### 8.1 实体关系

```text
InspectionPlan 1 ─── * InspectionRun
InspectionRun  0..1 ─── 1 InspectionRecord
InspectionRun  1 ─── * InspectionCheckResult
InspectionRun  * ─── * Issue（通过本轮命中关联表）
Issue          1 ─── * IssueEvent
Issue          1 ─── * IssueScopeMembership
IssueEvent     0..1 ─── * NotificationDelivery
InspectionRun  0..1 ─── * NotificationDelivery
InspectionPlan * ─── * NotificationChannel
AdminSession   独立可撤销 Session
SecurityAuditLog 独立追加写审计
ResourceMetricState 每个资源或容器只保留最新状态
```

### 8.2 唯一约束

| 实体 | 唯一约束 |
|---|---|
| Issue | `(cluster_id, fingerprint)` |
| IssueScopeMembership | `(issue_id, scope_key)` |
| InspectionRun | `inspection_record_id` 非空时唯一 |
| InspectionCheckResult | `(run_id, check_code, scope_key)`；scope_key 必须与结构化 scope 匹配 |
| InspectionPlan | 规范化后的 `name` 唯一 |
| NotificationChannel | 规范化后的 `name` 唯一 |
| NotificationDelivery | `deduplication_key` 唯一 |
| ResourceMetricState | `(cluster_id, kind, namespace, name, container_name)` |
| AdminSession | `token_hash` 唯一 |

计划和渠道使用单独关联表，唯一 `(plan_id, channel_id)`。

Issue 与 Run 使用单独命中关联表，唯一 `(run_id, issue_id)`；该表只表示本轮命中，不表示 Issue 的唯一来源。

IssueScopeMembership 保存 `active/last_seen_run_id/last_seen_at/deactivated_at`。它是 Issue 跨 scope 恢复判断的内部依据，不替代 Run 命中关联表，也不进入公开 Issue DTO。

InspectionCheckResult 按真实 scope 拆分结果。Run 级 Coverage 可以汇总展示，但不能替代详情中的 scoped check_results，也不能用于跨 scope 恢复。

### 8.3 关键索引

- Issue：`status/severity/last_seen_at`、namespace、resource kind、source_check
- IssueScopeMembership：`(scope_key, active)`、`issue_id`
- IssueEvent：`issue_id/occurred_at`
- InspectionRun：`started_at/status/plan_id`
- InspectionPlan：`enabled/next_run_at`
- NotificationDelivery：`status/next_retry_at/created_at`
- SecurityAuditLog：`occurred_at/action/outcome`

### 8.4 删除规则

- 开放 Issue 不参与清理。
- 删除计划不删除历史 Run；`plan_id` 置空或使用受控软删除。
- 删除通知渠道不删除 Delivery；历史记录保留脱敏渠道标识。
- 删除或过期 Session 必须使 Token 立即失效。
- IssueEvent、SecurityAuditLog 和 Delivery 是历史事实，不级联到仍在保留期内的数据。

## 9. 模块边界与依赖方向

依赖方向固定为：

```text
API routes
  ├── auth/system service
  └── inspection orchestration
        ├── provider collection
        ├── resource evaluators
        ├── issue lifecycle
        ├── plan scheduler
        └── notification dispatcher

上述模块共同依赖 schemas 和 ORM；schemas 不依赖业务模块。
```

### Agent 02：资源巡检

- 实现 Provider 分层采集和资源 evaluator。
- 输出 `ProviderCollectionResult`、`CheckEvaluation`。
- Provider 只消费 `ProviderCollectionRequest.thresholds`，不得用 `configure_inspection_policy()` 或其他共享可变配置传递阈值。
- 同一运行的采集和 evaluator 必须使用编排层冻结的同一策略快照，特别是 Warning Event 与 Pod 重启窗口。
- 每个 CheckEvaluation 必须携带本次真实 scope 和匹配的 scope_key，issue_count 与候选问题数量一致。
- 不写 Issue/Run/Plan/Delivery。
- 不实现路由、调度和通知。

### Agent 03：平台安全与升级

- 实现 ORM、migration、加密、AdminSession、CSRF、审计、健康探针。
- `main.py` 提供统一 lifespan 扩展点。
- 不实现 Issue 生命周期、计划调度和通知投递。

lifespan 扩展点必须支持注册异步 start/stop hook，并保证：

1. migration 和安全配置通过后才执行 start hook。
2. stop hook 按注册逆序执行。
3. 某个 start hook 失败时应用不 Ready，并清理已启动 hook。
4. Agent 04 通过注册接口接入 scheduler，不修改 `main.py`。

### Agent 04：主动巡检与通知

- 消费 `CheckEvaluation`，实现生命周期、Run、Plan、调度和通知。
- 按 IssueScopeMembership 的 active 语义实现跨 scope 恢复，禁止在 Issue 表增加单一 scope_key。
- 每次巡检运行使用同一 policy snapshot 的 namespace_concurrency；每日清理使用任务启动时同一 snapshot 的 retention。
- 复用 Agent 03 的加密和审计，不另建安全实现。
- 最终接线公共 API router，保留平台路由。
- 通知只实现 generic webhook 和飞书群自定义机器人单向告警。

### Agent 05：前端

- 只消费冻结契约。
- 不根据 Kubernetes 原始字段重新推断健康。
- 覆盖 loading、empty、error、permission denied、partial success。
- 确认操作明确提示“确认不等于恢复”。

### 公共文件接线

- schema：本文件及 `backend/app/schemas/v1_1.py` 为冻结源。
- ORM/model export：Agent 03。
- `main.py`、安全配置、lifespan：Agent 03。
- 公共 API router：Agent 03 先接安全和系统状态；Agent 04 后续 rebase 并保留，再接 Issue/Run/Plan/Notification。
- 前端 API 类型和 client：Agent 05。
- 集成使用 rebase，不创建 merge commit。

## 10. 前端类型一一对应

Agent 05 在 `frontend/src/api/types.ts` 使用下列同名联合类型：

| Pydantic | TypeScript |
|---|---|
| `IssueSeverity` | `"critical" \| "warning" \| "info"` |
| `IssueStatus` | `"open" \| "recovered"` |
| `IssueSortMode` | `"priority" \| "duration" \| "last_changed"` |
| `HealthStatus` | `"healthy" \| "warning" \| "critical" \| "unknown"` |
| `CheckStatus` | `"passed" \| "abnormal" \| "skipped" \| "failed"` |
| `InspectionTrigger` | `"manual" \| "scheduled"` |
| `InspectionRunStatus` | `"queued" \| "running" \| "succeeded" \| "partial" \| "failed"` |
| `NotificationChannelType` | `"generic_webhook" \| "feishu_custom_bot"` |
| `NotificationDeliveryStatus` | `"pending" \| "delivering" \| "succeeded" \| "failed" \| "suppressed"` |

规则：

- Python `datetime` 对应 ISO 8601 `string`。
- Python `int` 对应 `number`。
- `T | None` 对应 `T | null`。
- `Page[T]` 对应 `{items:T[]; total:number; page:number; page_size:number}`。
- Issue 时间线对应 `Page<IssueEvent>`，前端按页加载，不把全部事件写入 Issue。
- Issue 排序参数只能使用 `IssueSortMode`，不得在当前页再次改变服务端顺序。
- Response 类型不得包含 SecretStr 写入字段。
- UI 必须展示 `unknown/skipped/failed/partial`，不能统一映射为“正常”或“失败”。

## 11. 新增运行依赖评估

Agent 03 负责最终写入 `backend/pyproject.toml` 和锁定构建结果，建议兼容范围如下：

| 依赖 | 建议范围 | 用途 | 许可证 | 镜像与构建影响 |
|---|---|---|---|---|
| Alembic | `>=1.13,<2.0` | SQLite baseline 和版本化 migration | MIT | 纯 Python 为主；增加 migration CLI 和脚本 |
| cryptography | `>=43,<47` | TLS 证书/私钥校验、敏感配置对称加密 | Apache-2.0/BSD-3-Clause | 有平台 wheel；需验证 amd64/arm64 镜像 |
| argon2-cffi | `>=23.1,<26` | 管理员密码哈希校验 | MIT | 包含底层 binding；需验证多架构 wheel |
| HTTPX | `>=0.27,<1.0` | Webhook/飞书发送，明确 timeout 和 redirects | BSD-3-Clause | 当前仅为 dev 依赖，需提升为 runtime |
| APScheduler | `>=3.10,<4.0` | 单进程固定间隔和每日调度 | MIT | 纯 Python；4.x API 不兼容，因此上限 `<4` |

决策：

1. 不新增外部数据库、消息队列、Prometheus 或飞书 SDK。
2. 飞书 V2 Webhook 直接复用 HTTP 客户端。
3. 不新增 Cron 解析库；v1.1.0 计划只支持固定间隔和每日时间。
4. 密码算法不自研，默认 Argon2id。
5. 加密使用 cryptography 提供的认证加密能力，不自研加密算法。
6. 镜像构建必须验证 Python 3.11、amd64 和 arm64 wheel；若发生源码编译，不得临时把编译工具留在最终镜像。
7. 最终锁定版本前执行依赖许可证、漏洞和镜像体积检查，并在质量报告记录实际版本。

## 12. 验收要点

契约验收至少确认：

1. 正常、异常、跳过和失败四种 Coverage 可表达。
2. fingerprint 不受文案、severity 和时间变化影响。
3. fingerprint 拒绝空 cluster_id/source_check，recovered_at 不早于 last_seen_at。
4. 检查 failed/skipped 时旧 Issue 不恢复，恢复范围只取 CheckEvaluation.scope。
5. acknowledgement 不改变 Issue status。
6. API Response 的 details/facts 不含完整 Webhook、签名密钥、密码和 Session Token。
7. 飞书创建只接受官方 HTTPS V2 Webhook，且不含应用机器人、单聊、消息接收和回调字段。
8. Evidence 拒绝原始日志字段和超过 64 KiB 的 Issue 证据。
9. Provider 分层请求不能在 status 层读取 Event 或 Log。
10. Notification Delivery 可以表达失败和重试，但不保存原始响应。
11. 必需组件、全部 PRD 默认阈值、namespace 并发度和四类数据保留期可通过 Settings 新增字段配置，旧 PUT 不重置策略。
12. InspectionCheckResult 具有明确 run、check_code、scope 和稳定 scope_key；namespace 列表换序不改变 key。
13. Run 详情返回 scoped check_results，同一检查不同 namespace 的状态不会互相覆盖。
14. Node NotReady 宽限可配置，默认 0 表示立即 critical。
15. Issue 时间线使用 Page[IssueEvent] 按 occurred_at/id 降序分页，Issue 本身不无限内嵌事件。
16. Issue 三种受限排序在服务端全结果集执行后分页，并使用 id 作为最终 tie-breaker。
17. ProviderCollectionRequest 携带不可变阈值快照；并发运行不通过共享 Provider 配置串值，采集与判定使用同一快照。
18. 同一 Issue 的多个 scope membership 独立激活或失活；只有全部 membership 失活才恢复全局 Issue。
19. v1.0.0 四类巡检响应旧字段保持，issues/coverage 默认空数组且非空值不被响应模型过滤；InspectionRunResponse 通过嵌套包含。

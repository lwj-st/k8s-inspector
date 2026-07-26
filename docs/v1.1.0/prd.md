# K8s Inspector v1.1.0 产品需求文档

## 1. 文档信息

- 产品：K8s Inspector
- 版本：v1.1.0
- 版本主题：可信巡检与主动发现
- 文档状态：可进入研发
- 制定日期：2026-07-26
- 前置版本：v1.0.0

## 2. 背景

v1.0.0 已完成以下核心能力：

- 集群、名称空间和单 Pod 手动巡检
- Pod 状态、容器状态、事件、日志摘要和日志关键字命中
- Service、Ingress、TLS Secret、DaemonSet 基础展示
- 名称空间批量巡检和异常优先展示
- 故障模板录入、匹配和命中证据展示
- 关键字库、白名单和就地忽略
- 真实 Kubernetes 只读 Provider
- 单镜像、Helm、SQLite 单副本部署

当前产品已经能够帮助运维聚合证据，但还存在以下问题：

1. Service 和 TLS Secret 等对象没有完成真实健康判定，可能出现“假健康”。
2. 只看 Pod 无法判断 Deployment 发布卡住、Service 无 Endpoint、PVC Pending 等高频故障。
3. Node 主要检查 Ready，没有覆盖资源压力和容量风险。
4. CPU、内存数据在真实 Provider 中仍为 `n/a`。
5. 系统主要依赖人工点击，没有持续跟踪问题的首次发生、持续时间和恢复时间。
6. 没有定时巡检和通知，运维仍需主动打开系统才能发现问题。

## 3. 产品目标

v1.1.0 必须实现以下目标：

1. **消除假健康**：没有执行成功的检查不能显示为健康。
2. **覆盖高频故障**：能够自动发现工作负载、访问链路、证书、存储、节点压力和资源使用问题。
3. **形成故障链路**：从异常入口下钻到关联对象和证据，不要求运维手工跨页面比对。
4. **主动发现问题**：支持定时巡检、问题去重、状态变化和通知。
5. **保持只读安全**：不修改 Kubernetes 资源，不自动执行修复命令。
6. **兼容 v1.0.0**：已有巡检、模板、关键字和白名单能力不能回归。
7. **达到可升级交付标准**：具备鉴权、敏感配置保护、正式数据库迁移、健康检查和升级说明。

## 4. 成功标准

### 4.1 产品指标

1. 本文定义的 P0 故障样例，自动识别率达到 100%。
2. 已执行且证据明确的 P0 故障，不允许返回 `healthy`。
3. 同一问题连续出现时只保留一个问题实例，并更新持续时间和最后发现时间。
4. 新增问题、严重程度升级和问题恢复能够在一个巡检周期内产生状态变化记录。
5. 定时巡检不要求用户保持页面打开。
6. 所有巡检结果都能区分 `通过`、`异常`、`跳过`、`检查失败`。

### 4.2 质量指标

1. 后端、前端和 Helm 全量测试通过。
2. 新增健康判定必须具有异常、正常、跳过和采集失败测试。
3. v1.0.0 API 字段不删除、不改变原有语义；新增字段采用向后兼容方式。
4. Kubernetes RBAC 继续只包含读取权限；Secret 和 ConfigMap 按最小权限只授予实际需要的 `get`，不授予写权限。
5. 通知配置中的密钥、签名 Secret、完整 Webhook 地址不得出现在 API 响应、日志或前端页面中。
6. 生产模式未配置管理员鉴权、Session Secret 或配置加密密钥时，应用不得进入 Ready。
7. v1.0.0 数据库能够通过正式迁移升级到 v1.1.0，原有模板、白名单、关键字和历史记录保留。

## 5. 用户角色与核心场景

### 5.1 用户角色

本版本继续只考虑一个管理员角色：

- 实施运维
- 平台运维

### 5.2 核心场景

#### 场景 A：发布后服务不可用

Deployment 显示副本不足，部分 Pod 启动失败，Service 没有 Ready Endpoint。系统应展示相互关联的问题和完整证据链；没有确定性规则时，不强行声称其中某一项是唯一根因。

#### 场景 B：Pod 正常但访问失败

Pod 处于 Running，但 Service selector 选不中 Pod，或 EndpointSlice 没有 Ready Endpoint。系统必须识别，不得把 Service 固定显示为健康。

#### 场景 C：证书即将过期

Ingress 引用的 TLS Secret 存在，但证书将在 30 天内过期。系统应提前告警，并展示域名、Secret、到期时间和剩余天数。

#### 场景 D：存储导致 Pod Pending

PVC 长时间处于 Pending，Pod 事件出现挂载或绑定失败。系统应把 PVC、Pod 和事件关联展示。

#### 场景 E：节点压力引起业务抖动

Node 出现 `MemoryPressure`、`DiskPressure` 或 `PIDPressure`。系统应标记受影响节点，并列出节点上的异常 Pod。

#### 场景 F：无人值守发现

管理员配置每 10 分钟巡检一次。系统在问题首次出现时通知，持续未恢复时不重复轰炸，恢复时发送恢复通知。

## 6. 版本范围

### 6.1 P0：必须交付

### FR-01 统一巡检问题模型

系统必须把不同资源检查结果统一为问题 `Issue`，至少包含：

- `issue_code`：稳定的问题编码
- `fingerprint`：同一问题的稳定去重标识
- `severity`：`critical/warning/info`
- `status`：`open/recovered`
- `scope`：cluster、namespace、workload、pod、service、node 等
- `resource`：kind、namespace、name
- `summary`
- `reason`
- `suggestion`
- `evidence`
- `first_seen_at`
- `last_seen_at`
- `recovered_at`
- `occurrence_count`
- `source_check`
- `correlation_key`
- `acknowledged_at`
- `acknowledge_note`

要求：

1. 相同检查、相同对象、相同问题编码生成相同 fingerprint。
2. 连续巡检重复命中时更新原问题，不新增重复问题。
3. 上一轮存在、本轮检查成功且不再命中的问题转为 `recovered`。
4. 本轮检查失败或跳过时，不得把旧问题错误标记为恢复。
5. v1.0.0 现有结果结构继续保留，`issues` 以新增字段方式接入。
6. 运维可以确认问题并填写备注；确认不等于恢复，不改变实际健康状态。
7. 只有确定性的对象关系或模板规则才能设置相同 `correlation_key`；不得根据时间接近强行合并根因。

### FR-02 检查覆盖状态

每次巡检必须返回 `coverage`，每个检查项至少包含：

- `check_code`
- `name`
- `status`：`passed/abnormal/skipped/failed`
- `reason`
- `checked_objects`
- `duration_ms`

规则：

1. Metrics API 不可用时，资源指标检查为 `skipped`，不能显示健康。
2. RBAC 不足、API 超时和解析失败为 `failed`。
3. 资源不存在且业务规则允许跳过时为 `skipped`。
4. 页面必须明确显示覆盖率和未完成检查。

### FR-03 工作负载巡检

巡检以下对象：

- Deployment
- StatefulSet
- DaemonSet
- Job
- CronJob

判定要求：

1. Deployment 检查期望、副本、已更新副本、可用副本、不可用副本和 Conditions。
2. 识别 `ProgressDeadlineExceeded`、发布停滞和长期副本不足。
3. StatefulSet 检查期望副本、Ready 副本、Current/Update Revision。
4. DaemonSet 保留现有检查，并增加期望、Ready、Available、Unavailable 和调度失败证据。
5. Job 检查 Failed、BackoffLimitExceeded、超时和长期未完成。
6. CronJob 检查 suspended、最近调度时间和连续失败 Job；正常的 suspended 只展示状态，不作为故障。
7. 工作负载异常必须关联其 Pod；不得只使用 Pod 名称前缀猜测归属，优先使用 `ownerReferences`。
8. Deployment/StatefulSet 期望副本为 0、暂停发布和 DaemonSet 期望调度数为 0 时，按配置状态展示，不因副本为 0 直接告警。
9. 已成功完成的 Job 和正常 Completed/Succeeded Pod 不作为故障。
10. 集群巡检不得只依赖固定名称空间列表；应发现实际存在的工作负载。
11. Calico、Ingress Controller、GPU device plugin 等可选组件未安装时默认 skipped，不告警。
12. 管理员可以配置“必需组件”，使用 namespace、kind 和 label selector 定位；必需组件不存在时告警。

### FR-04 Service 与 EndpointSlice 巡检

检查以下内容：

- Service selector
- EndpointSlice
- Ready Endpoint 数量
- Service port 与 targetPort
- 后端 Pod Ready 状态

规则：

1. 普通 Service 有 selector 但没有 Ready Endpoint，至少为 `warning`。
2. 被 Ingress 引用的 Service 没有 Ready Endpoint，为 `critical`。
3. selector 选不中任何 Pod时，输出 selector 和相关证据。
4. `ExternalName` Service 不执行 EndpointSlice 健康判定，标记为 `skipped` 并说明原因。
5. 无 selector Service 允许人工维护 EndpointSlice；必须按实际 EndpointSlice 判定，不能直接报 selector 异常。
6. Headless Service 仍需检查 EndpointSlice。
7. 用户输入的 label selector 用于选择目标 Pod；不得直接把同一 selector 当作 Service、Ingress 等对象的 metadata selector。关联对象应通过真实 selector、backend 和 ownerReference 关系查找。

### FR-05 Ingress 访问链路巡检

系统必须构建以下只读关联链路：

`Ingress -> Service -> EndpointSlice -> Pod`

检查：

- Ingress backend Service 是否存在
- backend port 是否能在 Service 中找到
- Service 是否存在 Ready Endpoint
- TLS Secret 是否存在
- 显式指定的 IngressClass 是否存在
- Ingress 规则和资源证据

限制：

1. 不得仅根据 `status.loadBalancer` 是否为空判断 Ingress 健康。
2. v1.1.0 不从集群外主动发起 HTTP 探测。
3. Ingress Controller 自身状态继续通过工作负载和 Pod 检查完成。
4. 未显式指定 IngressClass 时只展示配置状态，不推断一定异常；显式指定但对象不存在时告警。
5. 非 Service 类型的 Resource Backend 标记为 skipped/unknown，并说明当前只支持 Service 链路，不得误判为 Service 缺失。

### FR-06 TLS 证书巡检

对 Ingress 引用的 `kubernetes.io/tls` Secret 执行：

- Secret 存在性检查
- `tls.crt` 和 `tls.key` 字段存在性检查
- X.509 证书解析
- 有效期检查
- SAN 与 Ingress host 匹配检查
- 证书与私钥匹配检查

默认严重程度：

- 已过期：`critical`
- 7 天内到期：`critical`
- 30 天内到期：`warning`
- 域名不匹配：`critical`
- 内容无法解析：`critical`

阈值允许通过系统配置调整。

### FR-07 存储巡检

巡检以下对象：

- PersistentVolumeClaim
- PersistentVolume
- StorageClass 基础关联信息
- Pod 与 PVC 挂载关系
- 相关 Warning Event

判定要求：

1. PVC `Pending`、`Lost` 或长时间未 Bound 必须告警。
2. PV `Failed` 必须告警，`Released` 长时间未回收必须提示。
3. Pod 事件中出现挂载、绑定、Attach、Mount 失败时，关联 PVC/PV 证据。
4. v1.1.0 不承诺通过 Kubernetes API 获取卷内文件系统实际使用率；没有可靠数据时必须标记 `skipped`，不能编造容量使用率。
5. StorageClass 使用 `WaitForFirstConsumer` 且当前没有消费 Pod 时，PVC Pending 属于预期状态，不告警。
6. PV reclaimPolicy 为 `Retain` 时，Released 表示等待人工回收；超过阈值只提示清理风险，不判断存储故障。

### FR-08 Node 健康巡检

除 Ready 外，新增检查：

- `MemoryPressure`
- `DiskPressure`
- `PIDPressure`
- `NetworkUnavailable`
- 不可调度状态
- taint 摘要
- allocatable 与 Pod requests 汇总
- 节点上的异常 Pod

规则：

1. `Ready=False/Unknown` 为 `critical`。
2. 任一 Pressure 条件为 `warning`；已造成驱逐、调度失败或业务不可用时升级为 `critical`。
3. 单次瞬时状态必须展示时间；连续状态由问题生命周期体现。
4. Node `spec.unschedulable=true` 单独作为维护状态展示，不直接告警；只有同时存在调度失败、容量不足或业务影响时创建问题。
5. taint 只作为调度证据，不因存在 taint 直接判断节点异常。

### FR-09 CPU 与内存指标巡检

优先读取 `metrics.k8s.io`：

- Node CPU、内存使用量
- Pod CPU、内存使用量
- requests、limits
- 使用量相对 request/limit 的比例

规则：

1. Metrics API 是可选依赖，不可用时不影响其他巡检。
2. 资源使用率为瞬时值，页面必须标注采样时间。
3. 高使用率只有连续三个定时周期超过阈值才创建持久问题；手动巡检仅展示瞬时风险提示。
4. `OOMKilled`、Evicted 和资源压力事件不受连续周期限制。
5. 默认阈值：相对 limit 达到 90% 为 warning；阈值可配置。
6. 容器未配置 limit 时，不基于“相对 limit”创建高使用率问题；可以展示相对 request 的比例和“未设置 limit”提示。
7. Metrics API 返回对象缺失或采样陈旧时显示 skipped/unknown，不使用旧值冒充当前状态。

### FR-10 定时巡检计划

支持创建和管理巡检计划：

- 计划名称
- 启用状态
- 巡检范围：全局、指定名称空间
- 执行间隔：5、10、30、60 分钟和每日
- 是否执行模板匹配
- 通知渠道
- 上次执行、下次执行和最近状态

约束：

1. v1.1.0 继续采用单副本部署，调度器运行在应用进程内。
2. 计划和执行记录持久化到 SQLite。
3. 应用重启后恢复计划；只补执行最近一次错过的任务，不批量补跑历史任务。
4. 同一计划禁止并发重入。
5. 手动巡检和定时巡检复用同一检查服务和健康语义。

### FR-11 问题状态与通知

通知触发：

- 新问题首次出现
- 问题严重程度升级
- 问题恢复
- 巡检任务整体失败

默认不通知：

- 同一问题未发生变化的重复巡检
- `info` 级问题
- 单个可选检查项被跳过
- 已确认但状态未变化的问题

v1.1.0 支持以下通知渠道：

- 通用 Webhook
- 飞书群自定义机器人 V2 Webhook

通用能力：

- 支持启停
- 支持连接测试
- 支持超时
- 失败最多重试三次
- 保存投递结果
- Webhook 地址在页面和 API 中脱敏
- 同一 fingerprint 在 30 分钟内反复打开和恢复达到三次时，发送一次抖动通知并进入 30 分钟冷却
- 生产环境默认只允许 HTTPS
- 禁止自动跟随重定向
- 生产环境必须配置 Webhook 目标主机或 CIDR 白名单，防止访问未授权的集群内地址、回环地址和云元数据地址

飞书群机器人适配要求：

1. 将统一通知对象转换为飞书消息格式，不要求用户编写 JSON 模板。
2. 默认发送非交互式消息卡片；卡片不支持时允许降级为文本通知。
3. 卡片按 critical、warning、recovered 和 inspection_failed 使用清楚但不过度刺眼的状态颜色。
4. 支持飞书群机器人安全设置中的签名密钥；Webhook 地址和签名密钥均加密保存并始终脱敏。
5. 支持“仅 critical 时提醒所有人”开关，默认关闭，避免告警打扰。
6. 发送前限制和裁剪消息体，序列化后的 JSON 不超过 30 KB；裁剪时保留结论、资源、时间、建议和详情链接。
7. 飞书返回失败、超时或限流时写入投递记录并按统一策略重试，不回滚巡检结果。
8. 连接测试发送明确标识为“测试通知”的消息，不创建虚假 Issue。

通知内容至少包含：

- 配置项 `CLUSTER_ID` 指定的集群或部署实例标识
- 问题状态
- 严重程度
- 问题摘要
- 资源范围
- 首次和最后发现时间
- 关键结构化证据摘要，不包含原始日志正文
- 处理建议
- 系统详情页链接

v1.1.0 的飞书范围仅为群告警通知，不包含：

- 飞书应用机器人
- App ID、App Secret 和 tenant access token 管理
- 向个人发送单聊通知
- 接收群消息或响应 @机器人
- 消息卡片按钮回调、在飞书内确认问题或执行修复

### FR-12 巡检工作台

首页升级为问题工作台，展示：

- 当前开放问题数量
- critical、warning 数量
- 最近恢复数量
- 最近一次巡检时间
- 巡检覆盖率
- 未执行或失败的检查项
- 按严重程度、持续时间和范围排序的问题列表

交互要求：

1. 默认优先展示开放问题。
2. 支持按严重程度、状态、名称空间、资源类型筛选。
3. 问题详情按“结论、影响、证据链、建议、时间线”展示。
4. 访问链路问题用紧凑链路展示 Ingress、Service、EndpointSlice 和 Pod。
5. 正常对象默认折叠。
6. 保留 v1.0.0 的模板匹配和白名单入口。
7. 定时巡检计划和通知配置放在系统配置区域，不占据日常排障主操作区。
8. 支持“确认问题”和确认备注，界面必须明确说明确认不会修改实际健康状态。
9. 对静态链路检查使用“配置链路正常/异常”，不得使用“访问正常”误导用户。

### FR-13 分层采集与负载保护

为避免定时巡检对集群和应用日志造成压力，采集分为两层：

1. 第一层只读取资源状态、对象关系和轻量字段。
2. 第二层仅对异常 Pod、模板明确要求的对象和用户主动发起的日志巡检读取 Event 和 Pod Log。

要求：

- 定时全局巡检默认不拉取所有正常 Pod 日志。
- 用户主动选择“日志巡检”时可以检查所选范围，但必须显示 Pod 数量和预计采集范围。
- 单次日志巡检默认最多 200 个 Pod，超过时要求缩小范围；上限可配置但不得无限制。
- 继续限制每容器日志行数、单 Pod 最大字节数和单次巡检总日志字节数。
- 日志全文或用于匹配的原始日志只允许在内存中短暂存在；持久化结果只保存命中上下文、摘要和截断标记。
- 单条 Issue 的持久化 evidence 默认不超过 64 KiB，超出时截断并标记。
- InspectionRun 记录 Kubernetes API 调用数、日志读取 Pod 数、采集字节数和耗时。
- 名称空间批量采集默认并发 3，配置上限 10。
- 单个对象采集失败只影响对应 Coverage，不中断其他范围。

### FR-14 管理访问安全

v1.1.0 提供单管理员本地鉴权：

- 管理员用户名和密码哈希通过 Kubernetes Secret 或环境变量配置。
- 登录成功后使用可服务端撤销的 HttpOnly Cookie Session；数据库只保存 Session Token 哈希。
- 生产 HTTPS 模式设置 `Secure` 和 `SameSite` Cookie。
- 默认空闲 30 分钟失效、最长 8 小时失效，阈值可配置。
- 退出登录立即撤销服务端 Session。
- 所有写接口必须校验 CSRF Token。
- 同一来源 10 分钟内连续登录失败 5 次后临时限流。
- 除存活探针、就绪探针和登录接口外，页面与 API 默认需要登录。
- `AUTH_MODE=disabled` 仅允许 mock、开发和 CI 环境使用。
- 使用 `APP_ENV=production` 明确定义生产模式。
- 生产模式缺少管理员、Session Secret 或加密密钥时，就绪检查失败并显示安全配置错误。
- v1.1.0 只支持单管理员，不支持多用户、角色和企业 SSO。

### FR-15 数据库升级与系统自检

数据库升级要求：

- 引入正式迁移工具，为 v1.0.0 数据库建立 baseline。
- v1.1.0 所有表和字段变化通过版本化 migration 完成。
- Kubernetes 部署在应用启动前执行 migration；迁移失败时应用不得启动。
- 升级文档必须包含备份、升级、验证和回退步骤。
- 不再为 v1.1.0 新字段增加临时 `PRAGMA + ALTER TABLE` 补丁。

系统自检至少展示：

- 应用版本
- 数据库连接和 schema version
- Kubernetes API 连接
- Provider 模式
- 调度器运行状态和最近心跳
- Metrics API 可用性
- 通知配置状态
- 最近一次巡检状态
- 配置校验错误

提供独立的存活和就绪探针：

- 存活探针只判断进程是否运行，不依赖外部 Kubernetes API。
- 就绪探针检查数据库 migration、安全配置和关键初始化状态。
- Metrics API 和 Webhook 不可用属于降级状态，不应导致应用退出。

### FR-16 Pod 运行与配置依赖巡检

在 v1.0.0 Pod 状态基础上补齐：

- Pod Ready Condition
- init container 状态
- 容器最近一次 terminated reason 和 exit code
- OOMKilled、Evicted、ImagePullBackOff、ErrImagePull
- 探针失败事件
- Pending/Unschedulable 原因
- 长时间 Terminating
- 重启次数在巡检周期内的增量
- 最近 Warning Event 的 reason、count 和时间
- Pod 引用的 ConfigMap、Secret、ServiceAccount、imagePullSecret 和 PVC 是否存在

规则：

1. Pod Phase 为 Running 但 Ready=False 时不能显示健康。
2. init container 失败必须独立展示，不得只显示主容器未启动。
3. 配置依赖只检查对象是否存在；API 返回对象后立即丢弃 data，不解析、不持久化、不记录、不展示非 TLS Secret 内容。
4. 对引用对象使用定点 `get`，不为存在性检查批量拉取全部 ConfigMap 或 Secret。
5. 重启告警依据时间窗口内增量，不能只根据历史累计值判断。
6. Pod 长时间 Terminating 默认阈值为 10 分钟，可配置。
7. Normal Event 只作为上下文，不创建问题；Warning Event 默认只统计最近 30 分钟，持续中的当前故障不受时间窗口影响。

### 6.2 后续版本候选

以下能力不属于 v1.1.0，不允许 Agent 自行实现：

- ResourceQuota 和 LimitRange 风险提示
- PDB 缺失或不可用预算提示
- Pod 副本跨节点分布风险
- CoreDNS 专项巡检
- GPU allocatable、requested 和 device plugin 关联汇总
- 问题列表 JSON 导出

### 6.3 不在 v1.1.0 范围

- 自动修复和自动执行 kubectl
- Kubernetes 资源写操作
- 宿主机 systemd 服务直接检查
- containerd、kubelet 主机进程真实状态采集
- 未通过 Kubernetes API 暴露的 etcd、kube-controller-manager、kube-scheduler 进程内部健康
- 集群外 HTTP、TCP、DNS 主动探测
- 动态验证 NetworkPolicy、CNI 数据面或 DNS 实际连通性
- Prometheus 强依赖和长期指标存储
- 多集群统一纳管
- 多用户、复杂权限体系和企业 SSO
- 对现有 LLM 补充能力进行扩展

说明：containerd、kubelet 和未暴露控制面进程的真实状态无法只依靠当前 Kubernetes API Provider 完成。相关组件如果以可见 Pod 运行，仍按工作负载和 Pod 规则巡检；否则需要 Node Agent、Node Problem Detector 或独立监控数据源。v1.1.0 不做“通过名称推断主机或控制面进程健康”的虚假实现。

## 7. 健康语义

### 7.1 对象状态

- `healthy`：所有必需检查成功且未发现问题。
- `warning`：存在需要关注的问题，但尚未确认整体不可用。
- `critical`：明确影响可用性、数据或安全。
- `unknown`：证据不足，无法判断。

### 7.2 检查状态

对象健康状态和检查执行状态必须分开：

- `passed`
- `abnormal`
- `skipped`
- `failed`

禁止行为：

1. 捕获异常后返回空数组并显示健康。
2. API 不可用时填入 `n/a`，但总体仍显示全部正常。
3. 资源不存在时不区分“不适用”和“采集失败”。

## 8. 问题编码

首批稳定编码至少包括：

- `WORKLOAD_REPLICAS_UNAVAILABLE`
- `WORKLOAD_ROLLOUT_STALLED`
- `REQUIRED_COMPONENT_MISSING`
- `JOB_FAILED`
- `CRONJOB_NOT_SCHEDULED`
- `SERVICE_NO_READY_ENDPOINT`
- `SERVICE_SELECTOR_MISMATCH`
- `INGRESS_BACKEND_NOT_FOUND`
- `INGRESS_BACKEND_PORT_INVALID`
- `INGRESS_CLASS_NOT_FOUND`
- `TLS_SECRET_NOT_FOUND`
- `TLS_CERT_EXPIRED`
- `TLS_CERT_EXPIRING`
- `TLS_HOST_MISMATCH`
- `TLS_KEY_MISMATCH`
- `PVC_NOT_BOUND`
- `PV_FAILED`
- `PV_RELEASED_STALE`
- `VOLUME_MOUNT_FAILED`
- `NODE_NOT_READY`
- `NODE_MEMORY_PRESSURE`
- `NODE_DISK_PRESSURE`
- `NODE_PID_PRESSURE`
- `NODE_NETWORK_UNAVAILABLE`
- `RESOURCE_USAGE_HIGH`
- `INSPECTION_CHECK_FAILED`
- `POD_NOT_READY`
- `POD_INIT_CONTAINER_FAILED`
- `POD_IMAGE_PULL_FAILED`
- `POD_PROBE_FAILED`
- `POD_CONFIG_REFERENCE_MISSING`
- `POD_TERMINATING_STUCK`
- `POD_RESTART_SPIKE`
- `POD_WARNING_EVENT`

问题编码发布后不得随意修改；文案调整不能改变 fingerprint。

## 9. API 与兼容性要求

### 9.1 兼容原则

1. 现有 `/api/v1` 路径保持不变。
2. 现有字段不删除。
3. 名称空间巡检、Pod 巡检和集群巡检新增 `issues`、`coverage`。
4. 新问题中心、计划和通知接口继续放在 `/api/v1`。

### 9.2 新增接口范围

必须提供：

- `GET /api/v1/issues`
- `GET /api/v1/issues/{id}`
- `POST /api/v1/issues/{id}/acknowledge`
- `GET /api/v1/inspection-runs`
- `GET /api/v1/inspection-runs/{id}`
- `GET /api/v1/inspection-plans`
- `POST /api/v1/inspection-plans`
- `PUT /api/v1/inspection-plans/{id}`
- `DELETE /api/v1/inspection-plans/{id}`
- `POST /api/v1/inspection-plans/{id}/run`
- `GET /api/v1/notification-channels`
- `POST /api/v1/notification-channels`
- `PUT /api/v1/notification-channels/{id}`
- `DELETE /api/v1/notification-channels/{id}`
- `POST /api/v1/notification-channels/{id}/test`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/session`
- `GET /api/v1/system/status`
- `GET /health/live`
- `GET /health/ready`

列表接口统一使用 `page/page_size`：

- `page` 默认 1
- `page_size` 默认 20
- `page_size` 最大 100
- 返回 `items/total/page/page_size`

最终字段由契约 Agent 固化，其他 Agent 不得各自定义不同结构。

## 10. 数据与保留策略

新增持久化对象：

- Issue
- IssueEvent
- InspectionRun
- InspectionCheckResult
- InspectionPlan
- NotificationChannel
- NotificationDelivery
- ResourceMetricState
- SecurityAuditLog
- AdminSession

默认保留：

- 巡检执行记录：30 天
- 已恢复问题：90 天
- 通知投递记录：30 天
- 安全审计记录：90 天

保留天数可配置，范围 7 至 180 天。清理任务每天执行一次，不删除开放问题和当前启用的计划。

## 11. 性能与可靠性

1. 名称空间巡检默认最多三个并发采集任务，可配置但不得超过十个。
2. Kubernetes 单次 API 请求继续使用超时控制。
3. 单个名称空间失败不能中断其他名称空间巡检。
4. 日志采集继续限制行数，不拉取完整历史日志。
5. 定时任务执行状态必须持久化。
6. 通知失败不能使巡检结果丢失。
7. 数据库仍按单副本 SQLite 设计，不支持多副本写入。
8. 定时巡检执行分层采集，不得对全部正常 Pod 默认读取日志。
9. 问题、执行记录和投递记录列表必须分页，不能一次返回全部历史数据。
10. 数据库升级使用版本化 migration；迁移失败不得带着不兼容 schema 启动。
11. 资源指标只保存每个对象最近状态和连续超阈值次数，不在 SQLite 中保存长期时序样本。
12. InspectionRecord、Issue 和 InspectionRun 不持久化完整 Pod 日志，只保存受限摘要和命中上下文。

### 11.1 Kubernetes 兼容范围

v1.1.0 正式支持：

- Kubernetes 1.34
- Kubernetes 1.35
- Kubernetes 1.36

要求：

1. 使用 `CoreV1`、`AppsV1`、`BatchV1`、`NetworkingV1`、`DiscoveryV1` 和 `StorageV1` 稳定 API。
2. CI 至少覆盖最低支持版本 1.34 和最高支持版本 1.36。
3. Kubernetes 1.33 及以下不作为 v1.1.0 商用支持范围；系统状态应展示实际服务端版本并给出“不在支持范围”提示。
4. Metrics API 仍为可选能力，不影响基础巡检支持。

## 12. 安全要求

1. Kubernetes 权限只读。
2. 不使用 Pod exec。
3. 非 TLS Secret 仅允许为引用存在性执行定点 get；收到对象后立即丢弃 data，不解析、不持久化、不写日志、不返回前端。
4. TLS 私钥只用于内存中匹配校验，不持久化、不写日志、不返回前端。
5. Webhook 地址、Webhook 签名 Secret（包含飞书群机器人签名密钥）和现有 LLM API Key 采用应用层加密后写入数据库，加密密钥由 Kubernetes Secret 或环境变量提供；API 只返回脱敏值。
6. 通知内容不得包含完整日志、Token、私钥和 Secret 数据。
7. 所有外部请求设置超时并限制重试。
8. 生产模式默认启用单管理员鉴权和 CSRF 防护。
9. 登录失败、配置变更、计划变更和通知测试写入安全审计记录，但不记录密码、Cookie、Token 和完整 Webhook。
10. 通知不携带原始日志正文；问题详情中的日志命中只保留受限上下文，并对常见 Token、密码和凭证格式进行脱敏。
11. Webhook 禁止自动重定向，并按配置的目标主机或 CIDR 白名单限制访问，防止 SSRF。
12. 详情页链接使用受信任的配置项生成，不使用未经校验的请求 Host。

## 13. 默认阈值

以下阈值必须可以通过系统配置调整：

- TLS warning：剩余 30 天
- TLS critical：剩余 7 天或已过期
- PVC Pending warning：持续 5 分钟
- PVC Pending critical：持续 30 分钟，或已经导致 Pod 无法启动
- PV Released stale：持续 24 小时
- Job 无 `activeDeadlineSeconds` 时的长期未完成提示：持续 60 分钟
- 资源使用 warning：相对 limit 达到 90%，连续三个定时巡检周期
- Node Ready 为 False 或 Unknown：立即 critical
- Pod Terminating warning：持续 10 分钟
- Pod restart spike warning：10 分钟内增加 3 次
- Warning Event 默认窗口：最近 30 分钟

配置缺失或取值非法时使用上述默认值，并在系统状态中显示配置校验结果。

Job 未配置 `activeDeadlineSeconds` 时，超过 60 分钟默认只产生 info 提示；只有明确失败 Condition、超过自身 deadline 或模板配置了预期时长时才升级为 warning/critical。

## 14. 验收故障目录

v1.1.0 必须提供自动化测试或 E2E fixture，覆盖：

1. Deployment 期望 3、副本可用 1。
2. Deployment `ProgressDeadlineExceeded`。
3. StatefulSet Ready 副本不足。
4. Failed Job。
5. Service selector 选不中 Pod。
6. Service 没有 Ready EndpointSlice。
7. Ingress 引用不存在的 Service。
8. Ingress backend port 不存在。
9. TLS Secret 不存在。
10. TLS 证书已过期。
11. TLS 证书 30 天内到期。
12. TLS SAN 不包含 Ingress host。
13. PVC Pending。
14. PV Failed。
15. Pod 出现 FailedMount 事件。
16. Node NotReady。
17. Node DiskPressure。
18. Metrics API 不存在时检查为 skipped。
19. 同一问题连续三次巡检只产生一个开放 Issue。
20. 问题消失后转为 recovered。
21. 检查失败时旧问题不被错误恢复。
22. 通知只在新问题、升级、恢复和任务失败时发送。
23. 定时全局巡检不会读取全部正常 Pod 日志。
24. 超过日志巡检 Pod 上限时明确拒绝并提示缩小范围。
25. v1.0.0 数据库通过 migration 升级后原数据可读。
26. migration 失败时应用不进入 Ready。
27. 生产模式缺少鉴权或加密配置时应用不进入 Ready。
28. 未登录访问受保护 API 返回 401，写接口缺少 CSRF 返回 403。
29. Webhook 地址、TLS 私钥、密码和 Session Secret 不出现在 API、日志和通知中。
30. 存活探针不因 Kubernetes API 暂时不可用而失败；就绪状态能显示降级原因。
31. EndpointSlice `ready=null` 按可用处理，并正确合并同一 Service 的多个 Slice。
32. 问题确认不改变 open/recovered 状态。
33. Webhook 不能通过重定向、回环地址、链路本地地址或未授权目标访问内部服务。
34. 通知不包含原始 Pod 日志正文，详情链接不受 Host Header 注入影响。
35. Running 但 Ready=False 的 Pod 被识别为异常。
36. init container 失败、镜像拉取失败和探针失败分别提供明确证据。
37. Pod 引用不存在的 ConfigMap、Secret、ServiceAccount、imagePullSecret 或 PVC 时告警。
38. 配置依赖检查不会批量读取或返回非 TLS Secret 内容。
39. Pod 重启告警按时间窗口增量判断，不因长期累计值产生误报。
40. Secret 和 ConfigMap RBAC 遵循最小权限，不包含 create、update、patch、delete。
41. 从 v1.0.0 升级后，已有 LLM API Key 被安全迁移为加密存储，API 仍只返回脱敏状态。
42. 原始 Pod 日志不会写入 SQLite；超出证据大小限制时结果明确标记已截断。
43. Normal Event 不创建问题，过期 Warning Event 不会持续造成误报。
44. 期望副本为 0、暂停发布、CronJob suspended、Node cordon 和正常 taint 不会单独产生故障误报。
45. 容器未配置 limit 时不产生虚假的“达到 limit 90%”告警。
46. `WaitForFirstConsumer` 且没有消费 Pod 的 PVC Pending 不告警。
47. reclaimPolicy=Retain 的 PV Released 只提示人工回收风险，不误报为存储故障。
48. 未配置 deadline 的长时间 Job 默认只产生 info，不直接判定失败。
49. 退出登录后原 Session 立即失效，数据库和日志中不保存明文 Session Token。
50. 显式指定但不存在的 IngressClass 被识别；Resource Backend 不会被误判为 Service 缺失。
51. 名称空间 label selector 不会错误过滤掉与目标 Pod 关联但 metadata label 不同的 Service。
52. 未安装的可选组件不会误报；配置为必需的组件缺失时能够告警。
53. 飞书群机器人渠道能够发送符合统一通知内容要求的非交互式告警卡片。
54. 飞书连接测试有明确测试标识，不创建 Issue；发送失败不会影响巡检结果。
55. 飞书 Webhook 地址和签名密钥不会出现在 API 响应、日志、前端页面或通知正文中。
56. 飞书消息体超过限制时安全裁剪并标记，不丢失问题结论、资源标识和详情链接。
57. “提醒所有人”默认关闭，启用后也只对 critical 告警生效。

## 15. 发布门槛

以下条件全部满足才能发布 v1.1.0：

1. P0 功能全部完成。
2. 验收故障目录全部通过。
3. v1.0.0 后端、前端、构建和 Helm 测试无回归。
4. Mock Provider 能稳定展示正常、异常、跳过和失败四类结果。
5. Kubernetes Provider 的新增 RBAC 经过 Helm lint 和只读权限复核。
6. 通知敏感信息检查通过。
7. UI 完成真实浏览器验收。
8. README、Helm values 和升级说明更新完成。
9. v1.0.0 SQLite 升级演练、数据备份和回退演练通过。
10. 生产安全配置、登录限流、Session Cookie 和 CSRF 验收通过。
11. 定时全局巡检的 API 调用量、日志读取量和耗时有验收记录。
12. Agent 文件越界审计通过，所有改动都有对应任务和 worklog。
13. Kubernetes 1.34 和 1.36 的 E2E 兼容验收通过。

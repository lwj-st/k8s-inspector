# K8s Inspector v1.1.0 巡检工作台 UX 设计

## 1. 文档状态

- 版本：v1.1.0
- 阶段：UX 设计门禁
- 日期：2026-07-26
- 适用对象：桌面浏览器和窄屏浏览器
- 设计依据：
  - `docs/v1.1.0/prd.md`
  - `docs/v1.1.0/architecture-contract.md`
  - `backend/app/schemas/v1_1.py`
- UX 设计已由总调度批准，第 2 节原契约阻塞项已关闭，前端实现与验证已完成。

## 2. 实现前置契约（已关闭）

原 UX 评审提出的问题时间线和跨分页排序两个阻塞项均已由契约 Agent 补齐，本节不再阻塞前端实现。

### 2.1 问题完整时间线：已关闭

最终接口：

```text
GET /api/v1/issues/{id}/events?page=1&page_size=20
Response: Page[IssueEvent]
```

最终规则：

1. 服务端按 `occurred_at DESC, id DESC` 稳定排序。
2. 首屏读取最近 20 条，时间线顶部显示最新事件。
3. 用户点击“加载更早记录”后读取下一页并追加到底部。
4. `opened/observed/severity_escalated/acknowledged/recovered/reopened` 使用冻结的 `IssueEvent`。
5. 接口失败只影响时间线区域，不隐藏问题当前结论和证据。
6. 没有事件时显示“暂无生命周期记录”，不能根据 Issue 状态伪造事件。

### 2.2 跨分页问题排序：已关闭

最终枚举：

```text
IssueSortMode = priority | duration | last_changed
```

| UI 选项 | 最终请求值 | 服务端排序 |
|---|---|---|
| 处置优先 | `priority` | open 优先、severity 降序、持续时间降序、id 降序 |
| 持续最久 | `duration` | open 优先、持续时间降序、severity 降序、id 降序 |
| 最近变化 | `last_changed` | 最新 IssueEvent 时间降序；无事件时使用首次发现时间；id 降序 |

排序在完整筛选结果上完成后再分页。前端只传 `sort` 并保持返回顺序，禁止重新排序当前页。

### 2.3 可实现范围

登录、Issue、IssueEvent、Coverage、InspectionRun、Plan、NotificationChannel、飞书群机器人、Settings 和 SystemStatus 均已有可落地的冻结 DTO 与 API。

## 3. 设计目标与边界

### 3.1 用户先回答五个问题

日常排障按以下顺序组织信息：

1. 现在有什么问题？
2. 哪些问题最需要先处理？
3. 影响哪个集群、名称空间和资源？
4. 后端实际看到了什么证据，哪些检查没有完成？
5. 下一步建议做什么？

### 3.2 健康语义边界

前端只展示后端结论，不读取 Kubernetes 原始字段重新判断健康：

- 对象健康：`healthy/warning/critical/unknown`
- 检查执行：`passed/abnormal/skipped/failed`
- 执行结果：`queued/running/succeeded/partial/failed`

强制规则：

1. `skipped` 显示“未检查/不适用”，不能显示绿色“正常”。
2. `failed` 显示“检查失败”，不能显示为对象异常，也不能显示为健康。
3. `unknown` 显示“无法判断”，不能显示为正常。
4. `partial` 显示“部分完成”，并给出未完成检查入口。
5. 确认问题只表示“已知晓”，不得改变 open/recovered 或健康状态。
6. Ingress 静态检查只使用“配置链路正常/异常/无法判断”，不得使用“访问正常”。
7. 后端没有返回 Coverage 时显示“服务端未提供覆盖信息”，不得显示 100%。

### 3.3 人性化原则

1. 异常和下一步操作优先，正常信息默认折叠。
2. 日常页面不出现计划、通知和阈值的大表单。
3. 一项功能只有一个主要入口；详情允许提供带上下文的快捷链接。
4. 主要按钮每个区域最多一个；危险或高打扰操作使用次级确认。
5. 内部枚举映射为中文，同时在详情中保留原始编码用于工单和检索。
6. 所有错误给出“发生了什么、数据是否保留、下一步怎么做”。
7. 列表筛选、页码、排序和滚动位置在打开、关闭详情后保持。

## 4. 信息架构

### 4.1 一级导航

```text
K8s 巡检台
├── 问题工作台
├── 手动巡检
│   ├── 状态巡检
│   ├── 日志巡检
│   └── 模板检查
├── 规则库
│   ├── 故障模板
│   └── 关键字与白名单
└── 系统设置
    ├── 巡检计划
    ├── 通知渠道
    ├── 巡检策略
    ├── 系统状态
    └── 基础配置
```

导航说明：

- 首页改为“问题工作台”，不再把名称空间选择器当首页。
- 当前 `AutoInspectionPage` 的名称空间状态巡检能力迁入“手动巡检 > 状态巡检”，不复制一套页面。
- 当前 `NamespaceInspectionPage/PodInspectionPage` 继续作为统一日志巡检入口。
- 当前 `DiagnosisPage`、模板、关键字和白名单入口保留。
- 计划、通知、必需组件、阈值和系统状态统一放入“系统设置”，不进入日常工作台主区域。

### 4.2 路由建议

| 路由 | 页面 | 兼容处理 |
|---|---|---|
| `/login` | 登录 | 新增 |
| `/` | 问题工作台 | 首页升级 |
| `/issues/:id` | 问题详情 | 支持通知详情链接 |
| `/inspections/status` | 状态巡检 | 承接当前首页能力 |
| `/inspections/namespace` | 日志巡检 | 保留现有地址 |
| `/inspections/pod` | 日志巡检 | 保留现有兼容入口 |
| `/diagnosis` | 模板检查 | 保留 |
| `/templates` | 故障模板 | 保留 |
| `/whitelists` | 关键字与白名单 | 保留当前双页签和已有能力 |
| `/settings?tab=plans` | 巡检计划 | 设置页签 |
| `/settings?tab=notifications` | 通知渠道 | 设置页签 |
| `/settings?tab=policy` | 必需组件、阈值、运行与保留 | 设置页签 |
| `/settings?tab=status` | 系统状态 | 设置页签 |
| `/settings?tab=basic` | 基础配置 | 保留当前 Settings 信息 |

页签写入 URL，刷新和分享后仍停留在原位置。

## 5. 全局页面框架

### 5.1 登录后框架

- 左侧：一级导航、产品名、当前集群标识。
- 顶部：页面标题、最近巡检状态、当前管理员菜单。
- 管理员菜单：Session 最长有效时间提示、退出登录。
- 主内容：最大阅读宽度，表格区域允许横向滚动。
- 全局降级条：仅在 SystemStatus 为 `degraded/not_ready` 时显示，可进入系统状态页。

不在所有页面重复显示全部系统组件状态。

### 5.2 登录与 Session

登录页字段：

- 用户名
- 密码
- “登录”按钮

流程：

1. 页面先请求 `GET /api/v1/auth/session`。
2. 已登录直接进入原目标地址；未登录展示登录页。
3. 登录成功保存响应中的 CSRF Token 到内存，并依赖 HttpOnly Cookie 维持 Session。
4. 不把 Session Token、密码或 CSRF Token写入 URL、日志和持久化存储。
5. 用户退出时调用 logout；成功或 Session 已失效都回到登录页。

状态反馈：

| 场景 | 表达 |
|---|---|
| 登录中 | 按钮“登录中…”，字段禁用，防止重复提交 |
| 用户名或密码错误 | 表单顶部“用户名或密码不正确” |
| 429 | “尝试次数过多，请稍后再试”；有 `Retry-After` 才显示等待时间 |
| 网络错误 | “暂时无法连接巡检系统，请检查网络后重试” |
| Session 即将到期 | 页面顶部轻提示，不阻断排障 |
| Session 过期/401 | 保存只读页面位置，跳转登录；重新登录后返回原页面 |
| 写操作遇到 401 | 不自动重放写请求；重新登录后让用户确认再提交 |
| 403 | 保留表单内容，提示“安全校验未通过，请刷新会话后重试” |

## 6. 问题工作台

### 6.1 首页信息层级

首屏从上到下：

1. 状态概览卡
2. 未完成检查提示
3. 开放问题列表
4. 已恢复问题折叠入口

概览卡：

| 卡片 | 数据 | 点击行为 |
|---|---|---|
| 开放问题 | `Page[Issue].total`，筛选 `status=open` | 打开开放问题筛选 |
| 严重 | `status=open,severity=critical` 的 total | 打开 critical 筛选 |
| 警告 | `status=open,severity=warning` 的 total | 打开 warning 筛选 |
| 最近一次恢复 | 最新 `InspectionRun.recovered_issue_count` | 查看该 Run |
| 最近巡检 | 最新 Run 状态与完成时间 | 查看执行详情 |
| 检查完成率 | 最新 Run Coverage 计算 | 打开 Coverage |

完成率只表示检查是否执行：

```text
(passed 数 + abnormal 数) / Coverage 总数
```

总数为 0 时显示 `--`。它不是健康分，也不能用来表示集群正常。

多个概览请求采用独立状态：

- 某张卡加载失败只显示该卡“暂时不可用”。
- 任何关键请求失败时，首页不能显示“全部正常”。
- 加载期间使用固定高度骨架，避免页面跳动。

### 6.2 未完成检查

最新 Run 含 `skipped/failed` 或 Run 为 `partial/failed` 时，在问题列表上方展示一条可展开提示：

- 标题：“最近巡检有 3 项未完成”
- 摘要：失败数量、跳过数量、影响的 scope
- 操作：“查看检查覆盖”

`skipped` 与 `failed` 分组展示，不混在开放 Issue 数中。

### 6.3 问题列表

默认显示开放问题。表格字段：

- 严重程度
- 结论
- 资源（Kind/name）
- 名称空间
- 状态
- 持续时间
- 最后发现
- 已确认状态
- 操作“查看详情”

筛选区：

- 严重程度：严重/警告/提示
- 状态：开放/已恢复
- 名称空间
- 资源类型
- 检查来源
- 排序：处置优先/持续最久/最近变化
- “清除筛选”

交互要求：

1. 筛选变化后回到第一页。
2. 筛选、排序和页码写入 URL query。
3. 名称空间和资源名过长时截断显示，悬停和聚焦可查看完整值。
4. 整行可进入详情，但行内按钮仍可独立聚焦和触发。
5. 只能使用第 2.2 节的服务端跨分页排序，禁止排序当前页。
6. 无结果时区分“当前没有问题”和“当前筛选无结果”。
7. 不提供批量确认，避免运维误把大量问题当成已处理。

### 6.4 问题详情

桌面端使用右侧宽抽屉，直接访问 `/issues/:id` 时使用完整页面；窄屏统一为完整页面。

内容顺序：

1. 结论
2. 影响范围
3. 证据链
4. 建议
5. 时间线
6. 确认信息

字段映射：

- 结论：`summary`、`severity`、`status`
- 影响范围：`scope`、`resource`、`cluster_id`
- 原因：`reason`
- 证据：`evidence`
- 建议：`suggestion`
- 时间线：第 2.1 节 IssueEvent 接口
- 当前确认：`acknowledged_at/acknowledge_note`
- 工单信息：`issue_code/source_check/fingerprint`，默认折叠

证据卡片：

- 标题使用 `Evidence.summary`
- 来源映射 `source`
- 观测时间 `observed_at`
- 事实表使用 `facts`
- 关联对象使用 `related_resources`
- `truncated=true` 显示“证据已按安全和长度限制截断”
- 不提供“查看完整原始日志”入口

证据为空时显示“本问题没有可展示的持久化证据”，不能生成占位日志。

### 6.5 问题确认

确认按钮只在开放和已恢复问题上显示“确认已知晓”，不使用“处理完成”。

确认对话框：

- 固定提示：“确认只表示你已知晓此问题，不会修改资源，也不会将问题标记为恢复。”
- 备注必填，最多 1000 字，显示剩余字数。
- 提交后更新确认时间和备注，Issue 状态徽标保持不变。
- 提交失败时保留备注。
- 已确认问题允许再次查看备注，本版本不设计取消确认，因为冻结 API 不支持。

## 7. 访问配置链路

### 7.1 展示方式

访问相关 Issue 在证据区使用紧凑横向链路：

```text
Ingress → Service → EndpointSlice → Pod
```

规则：

1. 只使用后端返回的 `Issue.resource`、`Evidence.related_resources`、`Evidence.summary/facts`。
2. 前端可以按 Kind 排列位置，但不根据对象字段自行推导是否健康。
3. 后端未提供的节点显示“未提供关联证据”，不能显示健康。
4. 每个节点展示 Kind、namespace/name 和后端证据摘要。
5. `failed/skipped/unknown` 使用对应状态，不折叠成正常。
6. 非 Service Resource Backend 显示“当前链路检查不适用”，不显示 Service 缺失。
7. 整体文案只使用“配置链路正常/异常/无法判断”。

### 7.2 窄屏

窄屏改为纵向步骤列表，箭头向下。节点内容和语义保持一致，不用横向滚动承载主要链路。

## 8. Coverage 与执行详情

### 8.1 Coverage 状态

| 原始值 | 中文 | 色彩与图标 | 含义 |
|---|---|---|---|
| `passed` | 已检查，无异常 | 绿色 + 对勾 | 检查执行成功且未发现问题 |
| `abnormal` | 已检查，发现异常 | 橙/红 + 感叹号 | 检查执行成功并产生 Issue |
| `skipped` | 未检查/不适用 | 灰色 + 跳过图标 | 可选依赖缺失或规则不适用 |
| `failed` | 检查失败 | 深红 + 断开图标 | 本应检查，但采集或解析失败 |

所有状态同时显示文字和图标，不能只靠颜色。

### 8.2 Run 列表和详情

工作台只显示最新 Run 摘要；完整记录放在设置区“巡检计划 > 执行记录”次级页签。

Run 摘要字段：

- `trigger/status/scope`
- `started_at/finished_at/duration_ms`
- `opened_issue_count/recovered_issue_count`
- `kubernetes_api_calls/log_pods_read/collected_log_bytes`

Run 详情：

1. 顶部展示执行结果。
2. `partial` 显示“主流程完成，但有检查跳过或失败”。
3. Coverage 按 abnormal、failed、skipped、passed 排序，正常项折叠。
4. 使用 `InspectionRunDetail.check_results` 展示真实 scope，不能用 Run 聚合 Coverage 覆盖局部失败。
5. `error_code/error_message` 只在失败时展示。
6. 采集统计明确说明它们是本次巡检负载，不是 Kubernetes 资源使用率。

## 9. 手动巡检

### 9.1 复用现有页面

- “状态巡检”复用当前名称空间发现、单名称空间巡检、全部名称空间巡检和证据抽屉。
- “日志巡检”复用当前统一范围选择页面。
- “模板检查”复用当前 Diagnosis 页面。
- 模板匹配、关键字命中忽略、白名单入口继续保留。

### 9.2 日志巡检范围保护

发起日志巡检前展示：

- 选择范围
- 预计 Pod 数
- 默认上限 200
- 是否读取当前日志/上次终止日志
- 提示“只保存命中上下文，不保存完整日志”

预计 Pod 数来源：

- 名称空间：Discovery 的 `pod_count`
- Label：Label Discovery 的 `pod_count`
- 单 Pod：1

超过上限时：

1. 主按钮禁用。
2. 提示“预计 268 个 Pod，超过本次上限 200 个”。
3. 提供缩小名称空间、Label 或选择单 Pod 的入口。
4. 后端仍必须执行最终上限校验；前端估算不能代替服务端保护。

## 10. 巡检计划

### 10.1 列表

每行展示：

- 名称
- 启用状态
- 范围
- 周期
- 下次执行
- 上次执行及状态
- 通知渠道数量
- 操作：立即运行、编辑、启停、删除

异常优先规则：

- 上次 `failed/partial` 的计划在原列表位置突出状态和“查看执行”入口，不由前端改变跨页顺序。
- 正在执行时“立即运行”禁用。
- API 返回 409 时提示“该计划正在执行，无需重复启动”。

### 10.2 新建和编辑

表单顺序：

1. 计划名称
2. 巡检范围：全部集群/指定名称空间
3. 执行周期：5/10/30/60 分钟/每日
4. 每日时间和时区（仅每日显示）
5. 是否执行模板匹配
6. 通知渠道
7. 启用状态

说明：

- 指定名称空间至少选择一个。
- 时区显示 IANA 值和当前本地示例。
- 创建成功后回到列表并高亮新计划。
- 编辑失败保留输入。
- 删除使用二次确认，并说明历史执行记录不会删除。

## 11. 通知渠道

### 11.1 渠道列表

展示：

- 渠道名称
- 类型：通用 Webhook/飞书群机器人
- 启用状态
- `endpoint_masked`
- 是否配置签名
- 超时
- 最近测试结果（仅本次交互可见；冻结列表 DTO 不提供历史测试字段）
- 操作：测试、编辑、启停、删除

任何页面都不显示完整 Webhook、签名密钥或密文。

### 11.2 通用 Webhook

创建字段：

- 名称
- Webhook 地址
- 可选签名密钥
- 请求超时 1–30 秒
- 启用

安全说明：

- 生产环境仅允许 HTTPS。
- 目标必须在服务端允许的 Host/CIDR 范围内。
- 系统不会跟随重定向。
- UI 不提供绕过白名单的开关。

编辑时：

- 当前地址只显示 `endpoint_masked`。
- 新地址输入框为空，说明“留空表示不更换”。
- 签名只显示“已配置/未配置”，可输入新值或选择“清除签名”。
- 渠道类型不可修改；要更换类型，需新建渠道并重新绑定计划。

### 11.3 飞书群机器人

创建字段：

- 名称
- 飞书群机器人 V2 Webhook
- 可选签名密钥
- 启用
- “仅 critical 时提醒所有人”，默认关闭
- 超时

固定说明：

> 仅向机器人所在飞书群发送告警；不接收消息，不支持单聊、卡片回调或在飞书内操作。

禁止出现：

- App ID
- App Secret
- tenant access token
- 单聊接收人
- 消息接收或回调地址
- 飞书内确认或修复按钮
- 自定义 JSON 模板输入

开启“提醒所有人”前显示二次说明：

> 开启后仅 critical 告警会提醒群内所有人，warning、恢复和测试通知不会提醒。该设置可能造成较强打扰。

用户确认后才开启；新建表单和重置操作都保持默认关闭。

### 11.4 连接测试

1. 渠道必须先保存，测试按钮才可用。
2. 点击后确认“将向目标群或 Webhook 发送一条明确标识的测试通知”。
3. 测试中按钮禁用。
4. 成功显示送达状态和时间。
5. pending/delivering 显示“已受理，仍在重试”。
6. 失败显示脱敏错误和建议，不显示下游原始响应。
7. 明确说明测试不会创建 Issue，也不会改变巡检结果。

## 12. 巡检策略

### 12.1 必需组件

页面先解释：

> 系统会自动发现可选组件；可选组件未安装不会告警。只有加入“必需组件”的对象在缺失时才告警。

每条策略字段：

- 名称
- 名称空间
- Kind
- Label Selector
- 启用

交互：

1. 用表格管理，新增和编辑使用侧边表单。
2. 三个定位字段同时匹配，表单下展示匹配规则。
3. 重复定位规则在提交前提示，最终以服务端 422 为准。
4. 关闭策略说明“停止缺失告警，不会删除 Kubernetes 资源”。
5. 清空列表需要二次确认。

### 12.2 阈值

按领域分组，避免一个长表单：

- TLS
- 存储
- Job
- 资源使用
- Pod
- Event
- Node

字段直接映射 `InspectionThresholds`。每个字段显示：

- 中文名称
- 单位
- 默认值
- 允许范围
- 当前影响

关联校验：

- TLS critical 天数不能大于 warning 天数。
- PVC warning 分钟不能大于 critical 分钟。
- 保存为整体提交，失败不得显示部分成功。
- “恢复默认值”先在表单中预览，用户再次保存后才生效。

### 12.3 运行与数据保留

- 名称空间并发数显示 Kubernetes API 压力提示，允许 1–10 的整数，默认 3。
- 巡检运行、已恢复问题、通知投递和安全审计四类保留周期分别配置，均允许 7–180 天。
- 已恢复问题保留项明确说明开放或仍活跃的问题不会清理。
- 运行设置和保留设置与阈值一起整体保存；前端先做中文范围校验，最终以服务端 422 为准。
- 文案明确说明新并发只影响之后启动的巡检，新保留周期只影响之后执行的每日清理任务。

## 13. 系统状态

顶部总状态：

- `healthy`：运行正常
- `degraded`：可以使用，但部分能力降级
- `not_ready`：关键初始化未完成

组件卡片：

- 数据库与 schema
- Kubernetes API
- Provider
- 调度器与心跳
- Metrics API
- 通知
- 最近巡检
- 配置校验

附加信息：

- 应用版本
- cluster_id
- Kubernetes 服务端版本
- 是否在 1.34–1.36 支持范围

组件状态：

| 原始值 | 中文 |
|---|---|
| `ok` | 正常 |
| `degraded` | 降级 |
| `failed` | 失败 |
| `unavailable` | 不可用 |

`metrics_api=unavailable/degraded` 说明“资源指标未覆盖，不影响其他巡检”，不能把整个应用显示为宕机。详情只渲染后端返回的脱敏 `message/details`。

## 14. 全局状态矩阵

| 状态 | 列表/卡片 | 页面行为 | 可用操作 |
|---|---|---|---|
| Loading | 骨架或行内进度 | 保留已有数据，标注刷新中 | 禁止重复提交 |
| Empty | 说明空的原因 | 不显示健康结论 | 提供创建、清除筛选或发起巡检 |
| Error | 错误摘要 + request_id（有则显示） | 旧数据标注“可能已过期” | 重试 |
| 401 | 跳转登录 | 记录返回地址 | 登录后返回 |
| 403 | 表单内容保留 | 提示安全校验失败 | 刷新会话后重新确认 |
| 404 | “对象不存在或已清理” | 不保留假详情 | 返回列表 |
| 409 | “计划正在执行/资源冲突” | 不重复创建 | 查看当前执行 |
| 422 | 字段旁中文校验 | 不清空表单 | 修正并重试 |
| 429 | 限流提示 | 不自动频繁重试 | 稍后重试 |
| Partial | 黄色“部分完成”提示 | 展示成功部分和未完成项 | 查看 Coverage/重试 |

页面级要求：

| 页面 | Empty | Error | Partial |
|---|---|---|---|
| 问题工作台 | 没有开放问题，但仍展示 Coverage | 各概览卡独立失败 | 未完成检查置顶 |
| 问题列表 | 区分无问题和筛选无结果 | 保留筛选条件 | 不适用 |
| 问题详情 | 证据或事件为空单独说明 | 当前结论可见，失败区单独重试 | Evidence 截断明确提示 |
| 计划 | 引导创建首个计划 | 列表读取失败可重试 | 上次 Run partial 明确展示 |
| 通知 | 引导创建渠道 | 测试失败不回滚配置 | delivering 显示处理中 |
| 系统状态 | 不使用通用空状态 | 读取失败不推断系统健康 | degraded 分组件展示 |

## 15. 关键流程

### 15.1 从告警到排障

```text
飞书/通用 Webhook
  → 使用受信任详情链接打开问题
  → 未登录则登录并返回原问题
  → 查看结论和影响范围
  → 查看异常证据与 Coverage
  → 查看建议
  → 填写确认备注
  → Issue 仍保持 open，直到后端巡检确认恢复
```

### 15.2 从工作台处理问题

```text
工作台 critical 卡片
  → 进入已筛选列表
  → 按处置优先排序
  → 打开详情抽屉
  → 查看证据链和时间线
  → 关闭详情
  → 返回原筛选、页码和滚动位置
```

### 15.3 配置主动巡检

```text
先创建通知渠道
  → 保存并发送测试通知
  → 创建巡检计划
  → 选择范围、周期和渠道
  → 启用
  → 列表显示下次执行时间
  → 首次执行后查看 Run 与 Coverage
```

## 16. 冻结 API 与字段映射

### 16.1 API 映射

| 功能 | API | 请求/响应 |
|---|---|---|
| Session 查询 | `GET /api/v1/auth/session` | `AdminSession` |
| 登录 | `POST /api/v1/auth/login` | `AuthLoginRequest -> AdminSession` |
| 退出 | `POST /api/v1/auth/logout` | CSRF，204 |
| 问题列表 | `GET /api/v1/issues` | `IssueListFilter -> Page[Issue]`；排序等待第 2.2 节补充 |
| 问题详情 | `GET /api/v1/issues/{id}` | `Issue` |
| 问题事件 | 待补 | 第 2.1 节 |
| 确认问题 | `POST /api/v1/issues/{id}/acknowledge` | `IssueAcknowledgeRequest -> Issue` |
| 执行列表 | `GET /api/v1/inspection-runs` | `InspectionRunListFilter -> Page[InspectionRun]` |
| 执行详情 | `GET /api/v1/inspection-runs/{id}` | `InspectionRunDetail` |
| 计划管理 | `/api/v1/inspection-plans` | `InspectionPlanCreate/Update/InspectionPlan` |
| 立即执行 | `POST /api/v1/inspection-plans/{id}/run` | `InspectionRun`，202 |
| 通知渠道 | `/api/v1/notification-channels` | `NotificationChannelCreate/Update/NotificationChannel` |
| 渠道测试 | `POST /api/v1/notification-channels/{id}/test` | `NotificationTestResponse` |
| 设置 | `GET/PUT /api/v1/settings` | 旧 Settings + `V11SettingsExtension` |
| 系统状态 | `GET /api/v1/system/status` | `SystemStatus` |

所有受保护写接口发送 `X-CSRF-Token`。API Client 必须携带 Cookie，并统一解析 `ApiError(code/message/request_id/details)`。

### 16.2 前端联合类型

前端必须与契约一一对应：

- `IssueSeverity = "critical" | "warning" | "info"`
- `IssueStatus = "open" | "recovered"`
- `HealthStatus = "healthy" | "warning" | "critical" | "unknown"`
- `CheckStatus = "passed" | "abnormal" | "skipped" | "failed"`
- `InspectionTrigger = "manual" | "scheduled"`
- `InspectionRunStatus = "queued" | "running" | "succeeded" | "partial" | "failed"`
- `NotificationChannelType = "generic_webhook" | "feishu_custom_bot"`
- `NotificationDeliveryStatus = "pending" | "delivering" | "succeeded" | "failed" | "suppressed"`

响应类型不得包含 `webhook_url`、`signing_secret`、密码、Session Token 或 token hash。

### 16.3 中文映射原则

- 界面主标签使用中文。
- Issue `issue_code`、Coverage `check_code` 和错误 `code` 在“技术详情”中保留原值。
- 未识别的新枚举显示“未知状态（原值）”，不能默认健康。
- 时间使用用户本地时区展示，同时允许复制 ISO 8601 原值。

## 17. 响应式布局

### 17.1 桌面端（≥ 1200 px）

- 固定侧边栏。
- 概览卡最多 6 列。
- 问题列表使用表格。
- 问题详情使用 560–720 px 右侧抽屉。
- 访问链路横向展示。

### 17.2 中等宽度（768–1199 px）

- 侧边栏可折叠。
- 概览卡 2–3 列。
- 表格保留关键列：严重程度、结论、资源、持续时间；次要字段进入展开区。
- 详情抽屉不超过视口 85%。

### 17.3 窄屏（< 768 px）

- 顶部菜单替代固定侧边栏。
- 概览卡单列或双列。
- 问题表格改为卡片列表，不要求用户横向滚动主内容。
- 详情使用完整页面。
- 访问链路纵向展示。
- 底部固定操作区只保留一个主要按钮。
- 表单字段单列，点击区域不小于 44×44 px。

## 18. 键盘与无障碍

1. 所有功能可只用键盘完成。
2. 抽屉和对话框打开后焦点进入标题或第一个字段，Tab 不离开当前浮层。
3. `Esc` 关闭非阻塞抽屉；有未保存表单时先确认。
4. 关闭浮层后焦点回到原触发按钮。
5. 表格行不只依赖双击；必须有可聚焦的“查看详情”按钮。
6. 状态使用文字、图标和颜色三种线索。
7. 表单错误与字段通过 `aria-describedby` 关联，提交失败后焦点移到首个错误。
8. 异步成功和失败反馈使用 `aria-live`，但持续刷新不反复朗读。
9. 骨架屏有可读的“正在加载”状态，装饰元素对辅助技术隐藏。
10. 页面标题层级连续，不能为了视觉大小跳过标题级别。
11. 颜色对比度达到 WCAG AA；聚焦轮廓始终可见。
12. 动画尊重 `prefers-reduced-motion`。

## 19. 关键文案

| 场景 | 推荐文案 |
|---|---|
| 无开放问题且 Coverage 完整 | “最近一次巡检未发现开放问题。” |
| 无开放问题但 Coverage 不完整 | “暂未发现开放问题，但有检查未完成，当前不能确认全部正常。” |
| 确认问题 | “确认只表示已知晓，不会恢复问题或修改 Kubernetes 资源。” |
| 配置链路通过 | “配置链路正常；本次未验证集群外真实访问。” |
| Metrics 不可用 | “资源指标未覆盖；其他巡检结果仍可使用。” |
| 飞书范围 | “仅发送群告警，不接收消息。” |
| 飞书测试 | “将发送一条测试通知，不会创建问题。” |
| Secret 已配置 | “已配置（内容始终隐藏）” |
| Run partial | “巡检部分完成，请查看跳过和失败的检查项。” |
| Evidence 截断 | “证据已按安全和长度限制截断。” |

禁止文案：

- “已处理”（用于 acknowledged）
- “访问正常”（用于静态 Ingress 链路）
- “全部正常”（Coverage 缺失、skipped、failed 或请求失败时）
- “暂无异常”（数据仍在加载时）
- “Webhook：完整地址”

## 20. 验收场景

UX 实现阶段至少覆盖以下 UI 断言和真实浏览器场景：

1. 未登录访问问题详情，登录后返回同一问题。
2. Session 过期不自动重放确认、计划修改或通知测试。
3. 401 跳转登录，403 保留表单并给出安全校验提示。
4. 工作台 critical 数量可进入已筛选列表。
5. 默认按“处置优先”服务端排序，critical/open 优先。
6. 切换“持续最久”和“最近变化”后跨页顺序稳定。
7. 关闭详情后保留筛选、排序、页码和滚动位置。
8. open 和 recovered 使用不同状态，acknowledged 不改变状态。
9. 确认对话框明确说明“确认不等于恢复”。
10. 问题详情按结论、影响范围、证据、建议、时间线展示。
11. 时间线可以加载更早记录，失败不隐藏当前问题详情。
12. 访问链路按 Ingress、Service、EndpointSlice、Pod 紧凑展示。
13. 配置链路通过时不出现“访问正常”。
14. passed、abnormal、skipped、failed 四种 Coverage 可区分。
15. skipped、failed 和 unknown 均不使用健康绿色。
16. Run `partial` 显示成功部分以及跳过、失败项。
17. 正常资源默认折叠，异常资源默认展开。
18. 日志巡检预计超过 200 Pod 时在发起前阻止并引导缩小范围。
19. 计划可以创建、编辑、启停、删除和立即运行。
20. 同计划运行中返回 409 时不创建重复执行。
21. 通用 Webhook 地址和签名始终脱敏。
22. 飞书配置没有 App ID、App Secret、单聊或回调字段。
23. 飞书不需要用户填写 JSON 消息模板。
24. 飞书签名可选且响应只显示“已配置/未配置”。
25. “仅 critical 时提醒所有人”默认关闭，开启前解释打扰范围。
26. 飞书测试通知有测试提示，不创建 Issue。
27. 通知测试失败不影响渠道配置和巡检结果。
28. 必需组件页面清楚区分可选组件与缺失即告警组件。
29. 阈值表单校验 TLS 和 PVC 阈值先后关系。
30. SystemStatus 显示数据库、Kubernetes API、Provider、调度器、Metrics、通知、最近巡检和配置。
31. Kubernetes 版本不受支持时明确提示，但不伪造其他组件失败。
32. loading、empty、error、401、403 和 partial 均有直接 UI 断言。
33. 360–430 px 窄屏无主要内容横向溢出。
34. 仅用键盘可以筛选、打开详情、确认问题、创建计划和测试通知。
35. 模板检查、故障模板、关键字和白名单入口保留。
36. Mock 数据覆盖 healthy、warning、critical、unknown、recovered、skipped、failed 和 partial。

## 21. 实现阶段门禁

进入前端实现前必须同时满足：

1. 总调度批准本文。
2. 第 2.1 节 IssueEvent 分页接口冻结并实现。
3. 第 2.2 节服务端跨分页排序契约冻结并实现。
4. 平台安全 Agent 已提供 Session、CSRF、SystemStatus 和 Settings 接口。
5. 主动巡检 Agent 已提供 Issue、Run、Plan 和 NotificationChannel 接口。
6. 冻结接口与 `backend/app/schemas/v1_1.py` 一致。

若实现时发现字段不足，必须停止对应功能并申请契约变更，禁止前端根据文案、时间接近或 Kubernetes 原始字段补造健康和根因结论。

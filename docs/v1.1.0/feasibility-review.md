# K8s Inspector v1.1.0 功能可实现性审查

## 1. 审查结论

v1.1.0 PRD 中保留的 P0 功能都可以在当前技术栈和单集群、单副本边界内实现。

审查遵循以下原则：

1. Kubernetes API 能直接提供或能够通过已有对象关系可靠计算。
2. 没有可靠数据源的能力不写入交付范围。
3. 只能静态判断配置链路时，不宣称验证了真实网络可达性。
4. 可选组件不存在时返回 `skipped`，不伪造健康结果。
5. 新功能必须具备升级、安全、性能和失败降级方案。

## 2. 逐项可实现性

| 功能 | 数据来源或实现方式 | 可实现性 | 明确限制 |
|---|---|---|---|
| Issue、Coverage 和生命周期 | SQLAlchemy + SQLite | 可实现 | 只在对应检查成功后自动恢复 |
| Deployment | `AppsV1Api` status/conditions | 可实现 | Pod 归属需沿 Pod -> ReplicaSet -> Deployment ownerReferences 解析 |
| Pod Ready、init container、终止原因 | Pod status/conditions/containerStatuses/initContainerStatuses | 可实现 | 重启突增需要跨巡检保存计数样本 |
| Pod Warning Event | Event type/reason/count/eventTime/lastTimestamp | 可实现 | Event 有保留周期，只能用于近期证据，不能作为长期历史源 |
| Pod 配置依赖存在性 | Pod spec + 对引用对象定点 get | 可实现 | API 对象可能携带 data，必须立即丢弃；不解析、持久化、记录或展示非 TLS Secret 内容 |
| StatefulSet、DaemonSet | `AppsV1Api` | 可实现 | 只判断控制器和副本状态，不判断应用业务响应 |
| 必需组件策略 | 全集群工作负载发现 + namespace/kind/label selector 配置 | 可实现 | 未配置为必需的可选组件不存在时不告警 |
| Job、CronJob | `BatchV1Api` | 可实现 | Cron 计算必须处理 `.spec.timeZone`、suspend 和 startingDeadlineSeconds |
| Service selector | `CoreV1Api` Service + Pod labels | 可实现 | 无 selector Service 不能按 selector 规则判断 |
| EndpointSlice | `DiscoveryV1Api` | 可实现 | 同一 Service 可能有多个 Slice，必须合并；`ready=null` 按 true 处理 |
| Ingress 后端链路 | `NetworkingV1Api` + IngressClass + Service + EndpointSlice | 可实现 | 只验证配置和 Ready Endpoint；Resource Backend 标记不适用；不能证明集群外真实 HTTP 可达 |
| TLS Secret | 指定 Secret + X.509/私钥解析 | 可实现 | 只读取 Ingress 实际引用的 TLS Secret；私钥仅在内存中校验 |
| PVC、PV、StorageClass | `CoreV1Api` + `StorageV1Api` + Event | 可实现 | Kubernetes API 不提供卷内文件系统实际使用率 |
| Node Condition | Node status/conditions/taints | 可实现 | 不能等同于宿主机所有服务正常 |
| Node requests 汇总 | Pod spec resources、init container、overhead | 可实现 | 是调度请求量，不是实际使用量 |
| CPU、内存使用 | `metrics.k8s.io` | 条件可实现 | Metrics Server 不存在时必须 skipped；不是长期时序数据 |
| 定时巡检 | 应用 lifespan + 持久化计划 + 单实例调度器 | 可实现 | 仅支持当前单副本架构，禁止多实例调度 |
| 问题去重与恢复 | 稳定 fingerprint + IssueEvent | 可实现 | 不做没有证据的跨对象根因合并，只做关联展示 |
| 通用 Webhook | 带超时的 HTTP 客户端 + 目标白名单 + 投递记录 | 可实现 | 禁止自动重定向；外部网络不可达时记录失败，不影响巡检结果 |
| 飞书群机器人告警 | V2 Webhook + 专用消息转换器 + 可选签名 | 可实现 | 只向机器人所在群发送通知；不接收消息、不处理卡片回调、不发送单聊 |
| 通知凭证和现有 LLM Key 加密 | 应用层对称加密，密钥来自 Kubernetes Secret | 可实现 | 通用 Webhook Secret 和飞书签名密钥均不明文保存；缺少加密密钥时敏感配置功能不可启用 |
| 单管理员鉴权 | 本地管理员 + 安全 Cookie Session + CSRF | 可实现 | v1.1.0 不做多用户、角色和企业 SSO |
| SQLite 正式升级 | Alembic baseline + revision + initContainer | 可实现 | 继续保持单副本和 RWO PVC |
| 分层采集 | 先状态后证据，异常对象再读取事件和日志 | 可实现 | 定时巡检默认不拉取所有正常 Pod 日志 |
| 问题工作台 | 现有 React 页面和新增 API | 可实现 | 前端只展示后端结论，不自行重新判断健康 |

## 3. 已从 v1.1.0 排除的不可可靠实现项

### 3.1 宿主机服务状态

当前 Provider 不能只通过 Kubernetes API 可靠判断：

- containerd systemd 状态
- kubelet systemd 状态
- 宿主机文件系统和 inode 真实使用率
- 未暴露为 Kubernetes 对象的 etcd、kube-controller-manager 和 kube-scheduler 进程内部健康

这些能力需要 Node Agent、Node Problem Detector、主机监控或 Prometheus 数据源，因此不进入 v1.1.0。如果控制面组件以当前账号可见的 Pod 运行，仍可按普通工作负载和 Pod 状态巡检。

### 3.2 真实网络连通性

静态读取 Ingress、Service 和 EndpointSlice 只能确认配置链路，不能证明：

- 集群外域名一定可以访问
- NetworkPolicy 没有阻断
- CNI 数据面一定正常
- DNS 查询一定成功
- 应用端口一定返回正确业务响应

v1.1.0 不创建探测 Pod、不执行 Pod exec，也不从集群外发起主动探测，因此页面文案必须使用“配置链路正常”，不能写“访问正常”。

### 3.3 长期资源趋势

Metrics API 只提供当前资源指标。v1.1.0 只保存每个对象最近状态和连续超阈值次数，不保存长期时序样本，不替代 Prometheus，也不提供任意时间范围的监控曲线。

### 3.4 自动根因推断

v1.1.0 允许用 `correlation_key` 展示相关问题，例如：

`Deployment 副本不足 -> Pod 异常 -> Service 无 Ready Endpoint`

但系统不能仅凭同时发生就断言唯一根因。除非模板明确匹配，否则不同问题保持独立 Issue，只做关联展示。

## 4. 新增依赖的可控范围

契约 Agent 必须评估并锁定兼容版本，预计需要：

- Alembic：SQLite 正式迁移
- cryptography：TLS 和 Webhook 配置加密
- 成熟的密码哈希库：管理员密码校验，禁止自研密码算法
- HTTP 客户端：Webhook 投递，可复用当前测试依赖或提升为运行依赖
- 调度库：优先选择成熟的单进程调度实现
- Cron 解析库：仅当选定调度库不能满足 CronJob 计划计算时引入

要求：

1. 不引入外部数据库、消息队列或 Prometheus 作为 v1.1.0 必需依赖。
2. 每个新增依赖必须说明用途、版本范围和许可证。
3. 依赖安装后必须进入镜像构建和 CI 验证。

## 5. 商用交付结论

满足以下条件后，v1.1.0 可以作为单集群、单副本、只读巡检软件交付：

1. 使用正式数据库迁移，不依赖临时 `ALTER TABLE` 补丁继续扩展。
2. 生产模式启用管理员鉴权，敏感配置加密。
3. 定时巡检采用分层采集和并发限制。
4. API、任务、通知和数据库失败都有可见状态。
5. 具备升级说明、备份说明和回归验收报告。
6. 明确不宣称主机服务、真实网络连通性和长期监控能力。
7. Webhook 有出站目标白名单和 SSRF 防护，通知不发送原始日志。
8. 飞书告警使用专用适配器生成消息，Webhook 地址和签名密钥加密保存；不把飞书应用机器人能力列入交付承诺。

## 6. 兼容范围

v1.1.0 商用支持 Kubernetes 1.34、1.35 和 1.36。

理由：

1. 当前项目使用 Kubernetes Python Client 36.x，与 Kubernetes 1.36 精确对应。
2. v1.1.0 使用的资源 API 在 1.34 至 1.36 均为稳定版本。
3. 正式支持范围必须通过最低和最高版本 E2E，而不是只依赖客户端兼容声明。
4. 1.33 及以下可以保持尽量兼容，但不作为本版本承诺的商用支持范围。

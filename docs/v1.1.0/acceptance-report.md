# K8s Inspector v1.1.0 验收报告

## 1. 结论

**不通过，当前不能作为商用 v1.1.0 发布。**

报告日期：2026-07-26。

当前主要阻塞：

1. 尚未在真实 Kubernetes 1.34 和 1.36 环境执行 E2E；CI 矩阵已配置，但配置不等于执行通过。
2. 尚未完成真实 v1.0.0 PVC 的备份、升级、完整性校验和回退演练。
3. 尚未在代表性大集群记录定时全局巡检的 API 调用量、日志读取量和耗时。

在以上阻塞关闭前，即使单元测试、前端构建和 Helm lint 通过，也不能给出“可以商用发布”的结论。

## 2. 状态说明

- **通过**：已有自动化、协议级 Mock、静态审计或浏览器证据，并已实际执行。
- **部分通过**：主体实现有测试，但缺少该条完整或精确场景。
- **未通过**：已复现缺陷，或明确违反验收要求。
- **环境阻塞**：需要真实 Kubernetes、PVC 或外部环境，当前未执行。

## 3. PRD 第 14 节逐项验收矩阵

| # | 验收故障/行为 | 状态 | 证据与备注 |
|---:|---|---|---|
| 1 | Deployment 期望 3、可用 1 | 通过 | 独立验收 fixture 验证 `WORKLOAD_REPLICAS_UNAVAILABLE`。 |
| 2 | Deployment `ProgressDeadlineExceeded` | 通过 | 独立验收 fixture 验证 critical `WORKLOAD_ROLLOUT_STALLED`。 |
| 3 | StatefulSet Ready 副本不足 | 通过 | 独立验收 fixture 验证统一副本判定。 |
| 4 | Failed Job | 通过 | 独立验收 fixture 验证 `JOB_FAILED`。 |
| 5 | Service selector 选不中 Pod | 通过 | 独立验收 fixture 同时验证 selector mismatch 与无 Ready Endpoint。 |
| 6 | Service 没有 Ready EndpointSlice | 通过 | `test_service_without_ready_endpoint_alerts_and_external_name_skips`。 |
| 7 | Ingress 引用不存在的 Service | 通过 | `test_ingress_backend_and_class_failures_are_reported_without_claiming_connectivity`。 |
| 8 | Ingress backend port 不存在 | 通过 | 同上，验证 `INGRESS_BACKEND_PORT_INVALID`。 |
| 9 | TLS Secret 不存在 | 通过 | 独立验收 fixture 验证 critical `TLS_SECRET_NOT_FOUND`。 |
| 10 | TLS 证书已过期 | 通过 | 独立验收 fixture 验证 critical `TLS_CERT_EXPIRED`。 |
| 11 | TLS 证书 30 天内到期 | 通过 | `test_tls_expiring_host_mismatch_and_key_mismatch_are_independent`。 |
| 12 | TLS SAN 不包含 Ingress host | 通过 | 同上，验证 `TLS_HOST_MISMATCH`。 |
| 13 | PVC Pending | 通过 | 独立验收 fixture 验证普通 Pending 告警；另有 WFFC 例外测试。 |
| 14 | PV Failed | 通过 | 独立验收 fixture 验证 critical `PV_FAILED`；另有 Retain/Released 语义测试。 |
| 15 | Pod 出现 FailedMount 事件 | 通过 | 独立验收 fixture 验证 Event 证据及 `VOLUME_MOUNT_FAILED`。 |
| 16 | Node NotReady | 通过 | 独立验收 fixture 验证超过宽限期后为 critical。 |
| 17 | Node DiskPressure | 通过 | `test_node_cordon_and_taint_alone_do_not_alert_but_pressure_does`。 |
| 18 | Metrics API 不存在时 skipped | 通过 | `test_metrics_unavailable_is_skipped_and_missing_limit_never_alerts`。 |
| 19 | 同一问题连续三次只产生一个开放 Issue | 通过 | 问题指纹、scope membership 和生命周期测试通过。 |
| 20 | 问题消失后 recovered | 通过 | `test_multi_scope_membership_delays_recovery_until_all_scopes_clear`。 |
| 21 | 检查失败时旧问题不错误恢复 | 通过 | `test_failed_check_does_not_deactivate_membership`。 |
| 22 | 仅新问题、升级、恢复和任务失败通知 | 通过 | 通知触发、抖动、冷却及 info 静默测试通过。 |
| 23 | 定时全局巡检不读取全部正常 Pod 日志 | 通过（自动化） | 状态、批量和无日志条件模板均验证零日志调用；日志模板只读取明确目标 Pod，相同 Pod 复用采集缓存。真实大集群负载仍是发布阻塞。 |
| 24 | 超过日志 Pod 上限时明确拒绝 | 通过 | 前端从 Settings 读取 `max_log_pods`，已知超限、数量未知或配置读取失败均硬阻断且无绕过按钮；后端动态上限、422 和零日志调用测试通过。 |
| 25 | v1.0.0 数据库 migration 后原数据可读 | 通过（自动化） | migration 自动化验证 baseline、历史表和 LLM API Key；真实 PVC 演练仍属发布阻塞。 |
| 26 | migration 失败时应用不 Ready | 通过（自动化） | 无密钥迁移失败不写入 head；Chart init container 失败会阻止主容器启动。 |
| 27 | 生产缺少鉴权或加密配置时不 Ready | 通过 | `test_production_missing_security_configuration_is_not_ready`。 |
| 28 | 未登录 401；写接口缺 CSRF 403 | 通过 | `test_login_session_csrf_logout_and_server_side_revocation`。 |
| 29 | Webhook、TLS 私钥、密码、Session Secret 不出现在 API/日志/通知 | 通过（自动化） | 巡检、诊断、Issue/evidence、InspectionRun 和通知链路均通过敏感值注入测试；API、历史和 SQLite 不出现原值，非敏感 `ERROR` 仍保留。 |
| 30 | K8s API 暂不可用不影响存活；就绪显示降级 | 通过 | 健康接口和 provider 初始化失败测试通过。 |
| 31 | EndpointSlice `ready=null` 可用且合并多个 Slice | 通过 | `test_endpoint_slice_merges_all_slices_and_ready_null_counts_as_ready`。 |
| 32 | 确认问题不改变 open/recovered | 通过 | `test_issue_acknowledgement_keeps_health_status_and_events_are_paged`。 |
| 33 | Webhook 防重定向、回环、链路本地和未授权目标 | 通过 | Webhook target policy 与每次重试重新校验测试通过。 |
| 34 | 通知不含原始日志，详情链接不受 Host 注入 | 通过 | 消息清洗和 `test_trusted_detail_url_ignores_request_host_by_requiring_static_base` 通过。 |
| 35 | Running 但 Ready=False 的 Pod 异常 | 通过 | `test_running_but_not_ready_pod_and_init_failure_are_abnormal`。 |
| 36 | init、镜像拉取、探针失败分别提供证据 | 通过 | 独立验收 fixture 验证三类 Issue 和证据 code 互不混淆。 |
| 37 | 引用缺失的 ConfigMap、Secret、ServiceAccount、imagePullSecret、PVC 告警 | 通过 | 独立验收 fixture 验证五类引用定点 get、缺失列表和 Issue 证据。 |
| 38 | 配置依赖不批量读取或返回非 TLS Secret | 通过 | 定点 `get`、立即丢弃 data 和 RBAC 测试通过。 |
| 39 | Pod 重启按时间窗口增量 | 通过 | `test_restart_delta_uses_windowed_samples_not_lifetime_total`。 |
| 40 | Secret/ConfigMap RBAC 最小权限 | 通过 | Helm 渲染仅 `get/list`，Secret/ConfigMap 仅定点 `get`；无写动词。 |
| 41 | v1.0 LLM API Key 安全迁移且 API 脱敏 | 通过（自动化） | `test_v100_plaintext_api_key_upgrades_encrypted_and_downgrades_for_rollback`。 |
| 42 | 原始日志不写 SQLite；超限有截断标记 | 通过（自动化） | InspectionRecord、DiagnosisRecord、Issue evidence 和 InspectionRun coverage 均通过清洗、限长和截断元数据门禁。 |
| 43 | Normal Event 不创建问题；过期 Warning 不误报 | 通过 | 事件时间窗口和当前故障例外测试通过。 |
| 44 | 零副本、暂停、CronJob suspended、cordon、正常 taint 不误报 | 通过 | 零副本、暂停、suspended、cordon、taint 测试通过；长时间 Job 的 info 边界见第 48 条。 |
| 45 | 未配置 limit 不产生 limit 90% 告警 | 通过 | Metrics missing-limit 测试通过。 |
| 46 | WaitForFirstConsumer 且无消费 Pod 的 PVC Pending 不告警 | 通过 | `test_wait_for_first_consumer_without_consumer_is_expected`。 |
| 47 | Retain 的 PV Released 只提示回收风险 | 通过 | `test_retain_released_pv_is_info_not_storage_failure`。 |
| 48 | 未配置 deadline 的长时间 Job 默认仅 info | 通过 | 独立验收 fixture 验证 info 且 reason 明确“不判定失败”。 |
| 49 | 退出后 Session 立即失效且不保存明文 Token | 通过 | Session 服务端撤销、审计 DTO 和数据库模型测试通过。 |
| 50 | 不存在 IngressClass 被识别；Resource Backend 不误判 | 通过 | 两个 Ingress 检查测试通过。 |
| 51 | namespace label selector 不错误过滤关联 Service | 通过 | `test_namespace_label_selector_is_only_passed_to_pod_list` 和关系采集测试通过。 |
| 52 | 可选组件不误报；必需组件缺失告警 | 通过 | required component policy 正反测试通过。 |
| 53 | 飞书群机器人发送非交互式告警卡片 | 通过（协议 Mock） | 卡片结构测试通过；无 App ID/App Secret。 |
| 54 | 飞书连接测试有标识、不创建 Issue；失败不影响巡检 | 通过（协议 Mock） | 渠道 API 和测试投递测试通过。 |
| 55 | 飞书 Webhook/签名不出现在 API、日志、页面或正文 | 通过（协议 Mock） | 渠道 API 脱敏、通知清洗和浏览器检查通过。 |
| 56 | 飞书消息超限安全裁剪且保留核心信息 | 通过（协议 Mock） | 30 KB 消息裁剪测试通过。 |
| 57 | 提醒所有人默认关闭且仅 critical 生效 | 通过（协议 Mock） | mention-all 及 info 静默测试通过；浏览器默认未勾选。 |

## 4. 测试与审计记录

### 4.1 已执行

- 所有实现 Agent 停止写入后，后端全量测试重新执行：354 项通过；仅有 1 个既有 Starlette/httpx 弃用警告。
- 日志分层、轻量发现、动态上限、诊断脱敏、契约和独立验收合并切片：182 项通过。
- 独立 PRD 资源目录与敏感证据全链路 fixture：17 项通过。
- 前端全量：14 个测试文件、80 项测试通过。
- 前端生产构建：75 个模块转换，构建通过。
- Helm lint：通过，仅有 Chart icon 建议信息。
- Helm `replicaCount=2`：按预期被模板拒绝。
- RBAC 渲染审计：10 组规则，只有 `get/list`，不含 `watch/create/update/patch/delete` 和 `pods/exec`。
- API 兼容：旧 `/api/v1` 路径保留，旧巡检响应仅新增 `issues` 和 `coverage`。
- 日志采集契约：namespace 旧请求省略 `include_logs` 仍兼容；状态/批量显式关闭日志，主动范围日志显式开启；单 Pod 下拉使用无巡检记录副作用的轻量 discovery。
- 动态日志预算：`inspection_policy.max_log_pods` 默认 200、允许 1 至 1000，Settings 持久化、后端执行和前端门禁使用同一配置源。
- 真实浏览器：登录、问题工作台、问题详情、计划、通知配置、系统状态和退出已检查；日志上限从 Settings 保存后立即生效，超限范围无绕过按钮且未发送巡检请求，单 Pod 下拉只调用轻量 discovery，单 Pod 巡检不受范围上限影响；最终构建在 390×844 下 `scrollWidth=clientWidth=390`，控制台无错误或警告。
- 飞书协议级 Mock：非交互卡片、签名、30 KB 裁剪、测试通知、失败重试、脱敏和 critical @all 已执行。
- 独立 PRD 资源目录 fixture：15 项通过，覆盖此前缺少的精确异常与正常边界。

### 4.2 尚未执行

- Kubernetes 1.34 和 1.36 的真实 KubeKey E2E。
- 真实 PVC 的 v1.0.0 备份、升级、完整性校验与回退。
- 大集群定时巡检的 API 调用量、日志 Pod 数、字节数和耗时基线。
- 真实测试飞书群的网络投递；当前 PRD 允许协议级 Mock，因此不单独作为阻塞。

## 5. Helm 与部署审计

- Chart `version` 和 `appVersion` 均为 `1.1.0`。
- SQLite 和进程内调度器要求单副本，模板显式拒绝其他副本数。
- 持久化开启时，migration init container 在主应用前执行。
- readiness 使用 `/health/ready`，liveness 使用 `/health/live`。
- 生产默认启用本地管理员鉴权、Secure Cookie、配置加密、可信详情地址和 Webhook allowlist 门槛。
- KubeKey CI 已加入 `v1.34.9` 与 `v1.36.2` 矩阵及服务端版本核对，但尚无执行结果。

## 6. 剩余发布阻塞与复验条件

| 阻塞 | 责任范围 | 复验条件 |
|---|---|---|
| Kubernetes 1.34/1.36 E2E | 质量与发布 | 两个矩阵实际成功，系统状态显示真实服务端版本 |
| PVC 升级/回退演练 | 平台安全与质量 | 备份、migration、数据校验、回退和 SHA 记录完整 |
| 定时巡检负载基线 | 自动化与质量 | 记录 API 调用、日志 Pod、字节和耗时，确认不拉全部正常日志 |

本地自动化、协议级 Mock、浏览器和静态门禁已经通过，但不能代替以上三个真实环境门禁。所有复验完成后，必须重新运行后端全量测试、前端全量测试和构建、Helm lint、浏览器回归，并更新本报告结论。

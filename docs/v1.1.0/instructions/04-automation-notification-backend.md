# Agent 04 指令：v1.1.0 主动巡检与通知后端

## Agent 名称

`v1.1-automation-notification`

## 开工条件

必须等以下 Agent 通过总调度验收：

- `v1.1-resource-inspection`
- `v1.1-platform-security-upgrade`

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/v1.1.0/architecture-contract.md`
- 当前 inspection、overview、settings、database 和 API router 实现

## 目标

实现 Issue 生命周期、定时巡检计划、执行记录、通用 Webhook 和飞书群机器人告警通知，让系统从人工触发升级为主动发现。

## 允许修改

- 新增的 `backend/app/services/issue_*`
- 新增的 `backend/app/services/inspection_plan_*`
- 新增的 `backend/app/services/notification_*`
- `backend/app/services/inspection_service.py`，只做统一 Issue/Run 接线
- 问题、执行记录、计划和通知专用 API route
- `backend/app/api/router.py`，保留平台路由并完成最终接线
- 主动巡检、Issue、计划和通知相关测试
- `worklog/v1.1-automation-notification-<实际日期>.md`

开工前必须把实际计划文件逐项写入 worklog。白名单外文件必须先申请总调度批准。

## 禁止修改

- `backend/app/providers/**`
- 资源健康判定模块
- `backend/app/security/**`
- `backend/app/db/**`
- `backend/migrations/**`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `frontend/**`
- `deploy/helm/**`

## 必须完成

1. 使用平台 Agent 已建立的 Issue、IssueEvent、InspectionRun、CheckResult、InspectionPlan、NotificationChannel、NotificationDelivery 和 ResourceMetricState 模型。
2. 实现稳定 fingerprint 和问题去重。
3. 实现首次发现、重复出现、严重程度升级和恢复。
4. 检查失败或跳过时禁止错误恢复旧问题。
5. 手动巡检和计划巡检统一接入 Issue 生命周期。
6. 实现单副本进程内调度器。
7. 实现应用重启后计划恢复和最近一次 missed run 补跑。
8. 同一计划禁止重入。
9. 实现问题、执行记录、计划和通知渠道 API。
10. 实现通用 Webhook 通知、超时、三次重试和投递记录。
11. 复用平台加密服务保存 Webhook，并实现响应脱敏。
12. 实现 7 至 180 天的数据保留和每日清理。
13. 通过平台 Agent 提供的 lifespan 扩展点注册调度器，不修改 `main.py`。
14. 实现问题确认和确认备注；确认不改变健康状态。
15. 实现确定性 `correlation_key`，不根据时间接近推断根因。
16. 实现告警抖动识别和冷却。
17. 实现资源指标连续三次超阈值判断。
18. 接入公共 API router，必须保留鉴权和系统状态路由。
19. Webhook 使用平台 Agent 提供的出站目标校验，生产环境只允许白名单内 HTTPS 目标，禁止自动重定向。
20. 通知只包含结构化证据摘要，不包含原始 Pod 日志正文；详情链接使用受信任配置生成。
21. InspectionRecord、Issue、Run 和 Delivery 写库前统一执行持久化 DTO 清洗，拒绝完整 Pod 日志并限制单条 evidence 大小。
22. 实现 `feishu_custom_bot` 专用适配器，把统一通知对象转换为飞书 V2 Webhook 消息，用户不需要编写消息 JSON。
23. 飞书默认使用非交互式消息卡片并支持文本降级；消息体超过 30 KB 时安全裁剪并标记。
24. 支持飞书群机器人可选签名密钥、连接测试和投递错误映射。
25. 支持“仅 critical 时提醒所有人”开关且默认关闭；warning、recovered 和任务失败不得触发提醒所有人。

## 调度规则

- 默认单次最多三个名称空间并发。
- 定时巡检必须调用资源 Agent 提供的轻量采集模式。
- 单个名称空间失败不终止其他范围。
- 调度任务先保存 running 状态，结束后保存 completed/partial/failed。
- 应用异常退出后遗留 running 任务在重启时标记 interrupted。
- 通知失败不回滚巡检和 Issue 状态。

## 通知规则

只对以下状态变化发送：

- opened
- severity_changed
- recovered
- inspection_failed

不得对每次重复命中发送通知。

连接测试必须使用专门测试消息，不创建虚假 Issue。

飞书群机器人只允许单向发送告警。不得实现飞书应用机器人、单聊、消息接收、事件回调、交互式确认或远程修复。

## 禁止

- 不修改 Kubernetes Provider 的资源判定。
- 不发送完整日志和 Secret。
- 不记录完整 Webhook 地址。
- 不允许调度器多实例并发运行；v1.1.0 明确单副本。
- 不实现自动修复。
- 不复制平台 Agent 的鉴权、CSRF、加密或 migration 实现。
- 不允许用户配置的 Webhook 绕过目标白名单访问集群内、回环或云元数据地址。

## 必测场景

覆盖 PRD 第 14 节的 19 至 22 项，并增加：

- 重启恢复计划
- 计划重入保护
- Webhook 超时和重试
- Webhook 地址脱敏
- 清理任务不删除开放问题
- 问题确认不改变健康状态
- 抖动通知与冷却
- 定时计划不会触发全量正常 Pod 日志读取
- SSRF、重定向和 Host Header 注入防护
- 通知不包含原始日志正文
- 数据库不包含原始 Pod 日志，证据超限时带截断标记
- 飞书消息格式转换、文本降级和 30 KB 裁剪
- 飞书 Webhook 与签名密钥脱敏
- 飞书连接测试不创建 Issue
- 飞书发送失败不影响巡检结果
- “提醒所有人”默认关闭且仅对 critical 生效
- 不存在飞书消息接收和卡片回调入口

## 验收命令

至少执行：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_settings_api.py
python3 -m pytest -q backend/tests
```

新增测试文件必须一并执行。

## Worklog

输出：

```text
worklog/v1.1-automation-notification-<实际日期>.md
```

在 worklog 中单独说明：

- 调度器启动和停止位置
- fingerprint 算法
- 恢复判定
- 敏感字段处理
- 飞书适配器、消息裁剪和错误映射
- SQLite 单副本假设
- 最终 `git diff --name-only` 与允许修改清单对比

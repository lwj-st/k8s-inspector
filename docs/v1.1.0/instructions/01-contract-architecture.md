# Agent 01 指令：v1.1.0 契约与架构

## Agent 名称

`v1.1-contract-architecture`

## 开工条件

收到总调度明确开工指令后开始。

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/superpowers/plans/2026-07-11-api-contract.md`
- 当前 `backend/app/schemas/`、`backend/app/models/` 和 `frontend/src/api/types.ts`

## 目标

冻结 v1.1.0 的统一数据契约和模块边界，让资源巡检、主动巡检和前端可以并行开发。

## 允许修改

- `docs/v1.1.0/architecture-contract.md`
- `backend/app/schemas/` 中 v1.1 契约文件
- `backend/tests/` 中新增或补充的契约测试
- `worklog/v1.1-contract-architecture-<实际日期>.md`

禁止修改白名单外文件；需要变更时先向总调度申请。

## 必须完成

1. 定义 Issue、IssueEvent、Evidence、Coverage、InspectionRun、InspectionPlan、NotificationChannel、NotificationDelivery、ResourceMetricState、AdminSession 和 SecurityAuditLog 的 Pydantic 契约。
2. 明确 v1.0.0 巡检响应如何以新增字段方式兼容 `issues` 和 `coverage`。
3. 固化问题编码、severity、issue status、check status 枚举。
4. 固化 fingerprint 输入，不把可变文案和时间放入 fingerprint。
5. 明确问题恢复规则：只有同一检查成功执行且问题未再命中，才能恢复。
6. 明确 API 请求响应结构、分页和筛选字段。
7. 给前端提供与后端一一对应的类型说明。
8. 定义数据库实体关系和唯一约束，但不实现完整调度业务。
9. 添加契约测试，覆盖正常、异常、跳过、失败和敏感字段脱敏结构。
10. 固化登录、Session、CSRF、系统状态、存活和就绪接口契约。
11. 固化 Agent 间的模块接口、依赖方向和公共文件接线责任。
12. 评估新增运行依赖的用途、版本范围、许可证和镜像影响。
13. 新建架构决策记录：

```text
docs/v1.1.0/architecture-contract.md
```

## 重点决策

- Issue 与每次巡检证据如何关联。
- `correlation_key` 只做确定性关联，不把同时发生的问题强行合并为根因。
- 手动巡检是否更新问题生命周期：默认更新，但必须记录 trigger=`manual`。
- 列表分页统一使用 PRD 定义的 `page/page_size`。
- 通知渠道响应如何只返回脱敏地址。
- 通知渠道类型固定包含 `generic_webhook` 和 `feishu_custom_bot`，并明确飞书配置、测试和投递结果契约。
- 飞书群机器人只定义单向通知契约，不引入 App ID、App Secret、消息接收或卡片回调契约。
- Webhook 目标白名单、DNS 解析、禁止重定向和 SSRF 防护契约。
- InspectionRun 和 v1.0.0 InspectionRecord 的兼容或迁移方式。
- 分层采集接口如何让 Provider 先返回轻量状态，再按需补证据。
- 原始日志只在内存中参与匹配，持久化 DTO 只能包含受限摘要、命中上下文和截断标记。
- 平台 Agent 如何提供 lifespan 扩展点，避免自动化 Agent 修改 `main.py`。
- 前端必须覆盖的 loading、empty、error、permission denied 和 partial success 状态。
- `APP_ENV`、`AUTH_MODE`、`CLUSTER_ID`、可信详情页地址和代理头信任边界。

## 禁止

- 不实现完整 Provider。
- 不实现后台调度循环。
- 不实现前端页面。
- 不实现 ORM 模型和 migration。
- 不修改 `frontend/**`、Helm 和业务 service。
- 不删除或重命名 v1.0.0 字段。
- 不把完整 Secret 或 Webhook URL 暴露到响应。

## 验收

至少执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_diagnosis_api.py
```

如果新增独立测试文件，一并执行。

## Worklog

输出：

```text
worklog/v1.1-contract-architecture-<实际日期>.md
```

worklog 必须附上开工文件计划、最终 `git diff --name-only` 和允许修改清单对比。

完成后停止，不进入实现阶段，等待总调度验收契约。

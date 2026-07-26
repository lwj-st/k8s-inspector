# K8s Inspector v1.1.0 文档索引

## 版本主题

v1.1.0 的主题是“可信巡检与主动发现”。

本版本在 v1.0.0 已具备的手动巡检、日志关键字、白名单和故障模板能力之上，重点解决三个问题：

1. 部分资源存在“未真正检查却显示健康”的情况。
2. 工作负载、访问链路、存储和节点资源等高频问题尚未形成完整证据链。
3. 巡检主要依赖人工触发，缺少定时执行、问题去重、状态跟踪、通用 Webhook 和飞书群告警通知。

## 文档列表

- [产品需求文档](./prd.md)
- [功能可实现性审查](./feasibility-review.md)
- [Agent 调度与交付计划](./agent-execution-plan.md)
- [Agent 01：契约与架构](./instructions/01-contract-architecture.md)
- [Agent 02：资源巡检后端](./instructions/02-resource-inspection-backend.md)
- [Agent 03：平台安全与升级](./instructions/03-platform-security-upgrade.md)
- [Agent 04：主动巡检与通知后端](./instructions/04-automation-notification-backend.md)
- [Agent 05：巡检工作台前端](./instructions/05-inspection-workbench-frontend.md)
- [Agent 06：质量验收与发布](./instructions/06-quality-release.md)

## 阅读顺序

所有 Agent 都必须先阅读：

1. 本索引。
2. `prd.md`。
3. `feasibility-review.md`。
4. `agent-execution-plan.md`。
5. 自己对应的 `instructions/*.md`。

如果文档与现有代码不一致，先在 worklog 中记录证据并交给总调度确认，不得自行扩大需求。

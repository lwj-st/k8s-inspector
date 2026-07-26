# Agent 06 指令：v1.1.0 质量验收与发布

## Agent 名称

`v1.1-quality-release`

## 开工条件

以下 Agent 已完成并提交 worklog：

- `v1.1-resource-inspection`
- `v1.1-platform-security-upgrade`
- `v1.1-automation-notification`
- `v1.1-inspection-workbench`

并且总调度已完成实现批次初验。

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/v1.1.0/architecture-contract.md`
- 四个实现 Agent 的 worklog
- 当前 README、Dockerfile、CI 和 Helm Chart

## 目标

独立验证 v1.1.0 是否满足 PRD，补齐发布文档，并给出明确的通过或不通过结论。

## 允许修改

- `docs/v1.1.0/acceptance-report.md`
- `docs/v1.1.0/upgrade-guide.md`
- `README.md`
- `deploy/helm/k8s-inspector/Chart.yaml`
- Helm values 中纯文档化示例和版本字段
- 新增的独立验收测试或 E2E fixture
- `.github/workflows/ci.yml`，仅限 Kubernetes 1.34/1.36 E2E 矩阵和 v1.1.0 验收步骤
- `deploy/kk/**`，仅限版本化 E2E fixture
- `worklog/v1.1-quality-release-<实际日期>.md`

## 禁止修改

- `backend/app/**`
- `frontend/src/**`
- 已有业务测试断言
- Kubernetes 资源判定、Issue 生命周期、鉴权和调度实现

发现缺陷必须记录证据并退回责任 Agent。白名单外文件必须先申请总调度批准。

## 必须完成

1. 对照 PRD 第 14 节逐项建立验收矩阵。
2. 运行后端全量测试。
3. 运行前端全量测试和构建。
4. 运行 Helm lint。
5. 检查新增 RBAC 只有只读权限。
6. 检查 API 向后兼容。
7. 检查检查失败和 skipped 不会显示健康。
8. 检查问题去重、恢复和错误恢复保护。
9. 检查通知敏感信息不泄露。
10. 检查 Webhook SSRF、重定向、目标白名单和可信详情页地址。
11. 检查管理员鉴权、Session、CSRF、限流和安全审计。
12. 检查 v1.0.0 数据库迁移、失败阻断、备份和回退。
13. 检查定时巡检不会读取全部正常 Pod 日志。
14. 使用真实浏览器验收登录、问题工作台、问题详情、计划、通知配置和系统状态。
15. 更新 README 的 v1.1.0 能力和配置说明。
16. 更新 Helm values 示例。
17. 将 Chart `appVersion` 更新为 `1.1.0`，Chart `version` 按语义化版本递增。
18. 新增升级说明：

```text
docs/v1.1.0/upgrade-guide.md
```

19. 新增最终验收报告：

```text
docs/v1.1.0/acceptance-report.md
```

20. 在 Kubernetes 1.34 和 1.36 上执行 E2E；如果环境无法提供，最终结论不得标记为“可以商用发布”。
21. 使用测试飞书群机器人或可验证的协议级 Mock，验收消息格式、签名、30 KB 裁剪、连接测试、失败重试、敏感信息脱敏和 critical 提醒所有人开关。
22. 确认产品没有要求 App ID/App Secret，也没有新增飞书消息接收、卡片回调或远程操作入口。

## 缺陷处理

- 所有业务缺陷退回责任 Agent。
- 质量 Agent 只能修改允许列表中的发布文档、版本元数据和新增验收 fixture。
- 不得删除失败测试、降低断言或把 failed 改为 skipped 来通过验收。

## 验收命令

至少执行：

```bash
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml
```

如果仓库已有 E2E 命令，按现有 CI 方式执行或说明环境阻塞。

## Worklog

输出：

```text
worklog/v1.1-quality-release-<实际日期>.md
```

最终结论只能是：

- 通过，可以发布 v1.1.0
- 不通过，列出阻塞问题和责任 Agent

worklog 必须附上最终 `git diff --name-only` 与允许修改清单对比。

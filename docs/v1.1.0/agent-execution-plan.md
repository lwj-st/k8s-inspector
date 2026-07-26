# K8s Inspector v1.1.0 Agent 调度与交付计划

## 1. 调度原则

v1.1.0 采用“契约先行、分域实现、统一验收”的方式。

总共需要六个 Agent，但不同时开工：

1. `v1.1-contract-architecture`
2. `v1.1-resource-inspection`
3. `v1.1-platform-security-upgrade`
4. `v1.1-automation-notification`
5. `v1.1-inspection-workbench`
6. `v1.1-quality-release`

## 2. 执行批次

### 批次一：契约冻结

只启动：

- `v1.1-contract-architecture`

该 Agent 完成统一 Issue、Coverage、InspectionRun、Plan 和 Notification 契约，输出决策记录并通过总调度验收。

契约未验收前，其他 Agent 不得修改正式 API 和数据库模型。

### 批次二：资源与平台基础

契约验收后启动：

- `v1.1-resource-inspection`
- `v1.1-platform-security-upgrade`
- `v1.1-inspection-workbench`，但本批次只允许产出 UX 设计稿，不允许修改前端代码

资源 Agent 和平台 Agent 按文件白名单并行开发。前端 Agent 先输出：

- `docs/v1.1.0/ux-design.md`
- 页面结构
- 关键流程
- 空状态、失败状态、权限状态
- 交互文案
- 移动和桌面宽度下的布局说明

UX 设计稿必须由总调度验收后才能进入代码实现。

### 批次三：业务实现与前端接入

资源与平台基础验收后启动：

- `v1.1-automation-notification`
- `v1.1-inspection-workbench` 前端实现阶段

主动巡检 Agent 负责公共后端接线；前端只消费已冻结 API。

### 批次四：质量与发布

所有实现 Agent 完成并分别留下 worklog 后，启动：

- `v1.1-quality-release`

质量 Agent 负责独立复核、测试和缺陷清单，不修改业务源代码。缺陷必须退回责任 Agent 修复。

## 3. 文件所有权

### Agent 01：契约与架构

主要所有权：

- `docs/v1.1.0/architecture-contract.md`
- `backend/app/schemas/`
- 新增契约测试
- 必要的数据模型设计稿

限制：

- 契约阶段不实现完整业务功能。
- 不改前端布局。

### Agent 02：资源巡检后端

主要所有权：

- `backend/app/providers/`
- `backend/app/services/` 中资源健康判定模块
- `backend/tests/test_kubernetes_provider.py`
- 新增资源巡检测试
- `deploy/helm/k8s-inspector/templates/clusterrole.yaml`

限制：

- 不实现调度器和通知发送。
- 不改前端。
- 不自行修改已冻结契约；需要变更时写入 worklog 并请求总调度。

### Agent 03：平台安全与升级

主要所有权：

- `backend/app/security/`
- `backend/app/db/`
- `backend/app/models/` 中 v1.1 新模型
- `backend/migrations/` 或契约确定的迁移目录
- `backend/app/core/config.py` 中安全和 migration 配置
- 鉴权、Session、CSRF、加密和安全审计相关路由与测试
- `backend/app/main.py` 中 lifespan、存活和就绪接线
- Helm Deployment、Secret 和 migration initContainer

限制：

- 不实现 Kubernetes 资源健康判定。
- 不实现 Issue 生命周期和巡检计划。
- 不改巡检工作台页面。
- 不自行修改已冻结 API；需要变更时请求总调度。

### Agent 04：主动巡检与通知后端

主要所有权：

- `backend/app/services/` 中 Issue 生命周期、调度和通知模块
- `backend/app/api/routes/` 中问题、计划和通知接口
- 通用 Webhook 与飞书群自定义机器人单向告警适配
- 数据清理和敏感信息处理
- 对应后端测试

限制：

- 不修改 Kubernetes Provider 的资源判定。
- 不改前端。
- 必须复用平台 Agent 提供的鉴权、加密和 migration 基础，不另建一套安全实现。
- 不实现飞书应用机器人、单聊、消息接收、卡片回调或远程操作。

### Agent 05：巡检工作台前端

主要所有权：

- `frontend/src/pages/`
- `frontend/src/features/`
- `frontend/src/components/`
- `frontend/src/api/`
- 前端测试和样式
- `docs/v1.1.0/ux-design.md`

限制：

- 不改后端。
- 不复制一套与后端不同的健康语义。
- 不删除 v1.0.0 的模板和白名单入口。
- 先交付 UX 设计稿，未经总调度批准不得开始改前端代码。

### Agent 06：质量验收与发布

主要所有权：

- 回归测试
- E2E fixture
- `README.md`
- Helm values 和 Chart 版本
- `docs/v1.1.0/upgrade-guide.md`
- `docs/v1.1.0/acceptance-report.md`
- `.github/workflows/ci.yml` 中 Kubernetes 兼容矩阵和 E2E 验收
- `deploy/kk/` 中版本化 E2E fixture
- 质量 worklog

限制：

- 所有业务缺陷退回原 Agent，不在验收阶段直接改业务源代码。
- 不放宽断言来掩盖失败。

## 4. 共享文件规则

以下文件容易冲突：

- `backend/app/services/inspection_service.py`
- `backend/app/schemas/inspection.py`
- `backend/app/api/router.py`
- `backend/app/models/__init__.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `deploy/helm/k8s-inspector/templates/deployment.yaml`
- `deploy/helm/k8s-inspector/templates/secret.yaml`
- `deploy/helm/k8s-inspector/values.yaml`

处理规则：

1. 契约 Agent 先冻结结构。
2. `main.py`、安全配置和 migration 接线由 `v1.1-platform-security-upgrade` 负责。
3. 平台 Agent 先在 API router 接入鉴权和系统状态；主动巡检 Agent rebase 后负责保留这些路由并完成最终公共 router 接线。
4. 前端公共 API 文件由 `v1.1-inspection-workbench` 负责。
5. 资源巡检 Agent 通过独立模块暴露结果，不修改公共 router、数据库模型和前端。
6. Helm RBAC 只由资源 Agent 修改；Helm Deployment 和 Secret 只由平台 Agent 修改；最终版本号只由质量 Agent 修改。
7. 合代码优先 rebase，不使用 merge commit。

## 5. 文件越界门禁

每个 Agent 的指令必须包含明确的“允许修改”和“禁止修改”路径。

执行规则：

1. 开工前将计划修改的文件写入 worklog。
2. 如果实现过程中需要修改白名单外文件，立即停止该部分工作并向总调度申请。
3. 未取得书面批准，不得以“顺手修复”“测试需要”或“重构方便”为理由越界。
4. 总调度验收时对照 `git diff --name-only` 和 Agent 文件白名单。
5. 发现越界改动时，该 Agent 本轮不通过；由总调度判断退回、拆分或重新授权。
6. 质量 Agent 不直接修业务代码，避免责任归属混乱。

## 6. Worklog 规范

每个 Agent 必须在 `worklog/` 新建：

```text
worklog/<agent-name>-<实际完成日期>.md
```

如果跨天继续工作，使用实际完成日期。

worklog 至少包含：

1. 阅读过的需求和指令路径。
2. 修改文件列表。
3. 实现内容。
4. 关键设计决定。
5. 未完成或需要总调度确认的问题。
6. 执行的测试命令。
7. 测试结果。
8. 是否存在兼容性、RBAC、安全或性能风险。
9. 建议下一个 Agent 重点复核的内容。
10. 计划文件清单与最终 `git diff --name-only` 对比。

禁止只写“已完成”。

## 7. Agent 通用交付要求

1. 先读 PRD、调度计划和自己的指令。
2. 修改前检查 `git status`，保留用户和其他 Agent 的已有改动。
3. 开工前列出允许修改的文件；白名单外改动必须暂停并申请。
4. 不扩大需求，不实现自动修复。
5. 所有采集失败必须显式表达，不能吞异常后返回健康。
6. 先补失败测试，再实现。
7. 所有新增交互必须覆盖 loading、empty、error、permission denied 和 partial success。
8. 页面文案必须使用运维能理解的中文，避免直接暴露内部枚举和无解释的英文缩写。
9. 只运行与自己任务相关的格式化工具，避免无关文件变化。
10. 交付前运行自己的切片测试。
11. 提交前 rebase 到总调度指定基线；不创建 merge commit。
12. 未得到总调度明确指令，不执行最终发布、不推生产镜像。

## 8. 总调度验收节奏

每个批次结束后总调度执行：

1. 阅读 worklog。
2. 查看 diff 和文件所有权。
3. 执行切片测试。
4. 检查契约一致性。
5. 检查文件越界、用户体验、安全、升级和性能证据。
6. 给出通过、返工或下一批指令。

任何一个 Agent 的“完成”不等于版本验收通过。

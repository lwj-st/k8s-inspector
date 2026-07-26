# Agent 03 指令：v1.1.0 平台安全与升级

## Agent 名称

`v1.1-platform-security-upgrade`

## 开工条件

必须等 `v1.1-contract-architecture` 的契约通过总调度验收。

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/v1.1.0/architecture-contract.md`
- 当前数据库初始化、Settings、FastAPI 启动、Helm Deployment 和 Secret

## 目标

建立 v1.1.0 的商用基础：正式数据库迁移、单管理员鉴权、敏感配置加密、安全审计和可靠的存活/就绪状态。

## 允许修改

- `backend/app/security/**`
- `backend/app/db/**`
- `backend/app/models/` 中契约定义的 v1.1 新模型和模型导出
- `backend/migrations/**` 或契约确定的迁移目录
- `backend/alembic.ini`
- `backend/app/core/config.py`
- 鉴权、健康检查和安全审计专用 model、route、service
- `backend/app/models/system_setting.py`、settings service/route，仅限现有 LLM API Key 加密迁移
- `backend/app/api/router.py`，仅用于接入鉴权和系统状态路由
- `backend/app/main.py`
- `backend/pyproject.toml`
- 对应后端测试
- `deploy/helm/k8s-inspector/templates/deployment.yaml`
- `deploy/helm/k8s-inspector/templates/secret.yaml`
- `deploy/helm/k8s-inspector/templates/configmap.yaml`
- `deploy/helm/k8s-inspector/values.yaml`

开工前必须在 worklog 中把实际计划文件逐项列出。

## 禁止修改

- `backend/app/providers/**`
- 资源健康判定服务
- Issue 生命周期、巡检计划和 Webhook 投递业务
- `frontend/**`
- `backend/app/schemas/**`，必须使用契约 Agent 已冻结的 schema；不足时申请契约返工
- Helm RBAC
- v1.0.0 模板、匹配器、关键字和白名单业务

白名单外文件必须先申请总调度批准。

## 必须完成

1. 为当前 v1.0.0 SQLite schema 建立 Alembic baseline。
2. 提供 v1.1.0 migration 基础和迁移测试。
3. Kubernetes Deployment 使用 initContainer 在应用启动前执行 migration。
4. migration 失败时主容器不得启动。
5. 实现单管理员登录、退出和 Session 查询，Session 可以服务端撤销。
6. Session Cookie 使用 HttpOnly、SameSite；生产 HTTPS 支持 Secure；数据库只保存 Token 哈希。
7. 所有写接口提供统一 CSRF 校验机制，业务路由后续只需复用。
8. 实现登录失败限流和安全审计。
9. 实现通用敏感配置加密服务，供通知 Agent 调用。
10. 加密密钥、Session Secret、管理员密码哈希从 Kubernetes Secret 或环境变量读取。
11. API、日志和异常不得返回上述敏感值。
12. 实现 `/health/live` 和 `/health/ready`。
13. 实现系统状态基础结构：版本、数据库、schema、安全配置和初始化状态。
14. `AUTH_MODE=disabled` 只允许 mock、开发和 CI；生产配置错误时 Ready 失败。
15. 提供 lifespan 扩展点，让主动巡检 Agent 可以注册调度器，不需要再次修改 `main.py`。
16. 按契约建立 v1.1 新 ORM 模型、唯一约束、索引和 migration；不实现 Issue、计划和通知业务逻辑。
17. 评估并锁定 Alembic、cryptography、HTTP 客户端和调度相关运行依赖，记录用途和许可证。
18. 在本 Agent worklog 中写明数据库备份、升级和回退基础方案，供质量 Agent 整理成正式升级文档。
19. 提供 Webhook 出站目标校验基础：主机/CIDR 白名单、回环和链路本地地址拒绝、可信详情页基础地址校验。
20. 将现有 LLM API Key 从明文列安全迁移为加密存储，兼容 v1.0.0 数据且 API 继续只返回脱敏状态。
21. Session 默认空闲 30 分钟、最长 8 小时失效并支持配置；退出后立即失效。
22. 通用加密服务必须支持飞书群机器人 Webhook 地址和可选签名密钥；不得引入或保存飞书应用机器人的 App ID、App Secret 和 access token。

## 商用要求

- 不自行设计弱化版 Token 登录。
- 不把密码或 Token 保存到 localStorage。
- 不使用明文密码。
- 不通过忽略 migration 错误继续启动。
- 不把 liveness 与 Kubernetes API、Metrics API 或 Webhook 可用性绑定。
- 加密服务必须有错误密钥、缺少密钥和密文损坏测试。
- 必须有 v1.0.0 明文 LLM API Key 升级为密文的迁移测试，测试输出不得打印原值。
- 出站目标校验必须覆盖 DNS 解析到未授权地址和 Host Header 注入。

## 验收

至少执行：

```bash
python3 -m pytest -q backend/tests
helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml
```

必须额外演练：

- 空 v1.1.0 数据库初始化
- v1.0.0 数据库升级
- migration 失败
- 未登录、登录失败限流、CSRF 失败
- 敏感字段脱敏
- 存活和就绪状态差异

## Worklog

输出：

```text
worklog/v1.1-platform-security-upgrade-<实际日期>.md
```

worklog 必须附上开工文件计划、最终 `git diff --name-only`、migration 演练结果和敏感信息检查结果。

完成后等待总调度验收，不得继续实现主动巡检或前端。

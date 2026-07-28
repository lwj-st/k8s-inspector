# K8s Inspector v1.1.0 升级与回退指南

## 1. 适用范围

本指南用于将单副本、SQLite 部署的 K8s Inspector v1.0.0 升级到 v1.1.0。

v1.1.0 会新增问题、计划、执行、通知、Session 和审计表，并把已有 LLM API Key 迁移为加密存储。升级必须能够同时恢复数据库、镜像、Helm values 和加密密钥，不能只回退镜像。

## 2. 升级前检查

确认以下条件全部满足：

1. 当前应用只有一个副本。
2. 已记录当前 release、namespace、镜像摘要、Chart 版本和 values。
3. SQLite 位于持久卷，不是临时目录。
4. 已准备 Argon2 管理员密码哈希、Session Secret 和 Fernet 配置加密密钥。
5. 已准备可信详情页基础地址及 Webhook 主机或 CIDR 允许列表。
6. 已确认 v1.1.0 镜像包含 `app.db.migrate`。
7. 已安排维护窗口；备份期间停止应用写入。

建议先保存当前部署信息：

```bash
helm get values RELEASE -n NAMESPACE --all > values-v1.0.0.yaml
helm get manifest RELEASE -n NAMESPACE > manifest-v1.0.0.yaml
kubectl get deployment,pod,pvc -n NAMESPACE -o wide > resources-v1.0.0.txt
```

将 `RELEASE` 和 `NAMESPACE` 替换为真实值。这些文件可能含内部地址，按生产配置文件保护，不要提交到 Git。

## 3. 备份

### 3.1 停止写入

先找到应用 Deployment，再停止副本：

```bash
kubectl get deployment -n NAMESPACE \
  -l app.kubernetes.io/instance=RELEASE
kubectl scale deployment/DEPLOYMENT -n NAMESPACE --replicas=0
kubectl wait -n NAMESPACE \
  --for=delete pod \
  -l app.kubernetes.io/instance=RELEASE \
  --timeout=180s
```

如果同一 release 还包含 Helm test Pod，应先删除已完成的 test Pod，避免误判仍有进程挂载数据库。

### 3.2 备份持久卷

优先使用存储平台提供的 CSI `VolumeSnapshot` 或等效快照，并记录快照 ID、PVC 名称和创建时间。快照必须在应用停止后创建。

如果平台没有快照能力，可创建一个只挂载该 PVC 的临时维护 Pod，再将数据库复制到受控备份位置。维护 Pod 必须：

- 使用与应用相同的 `runAsUser`、`runAsGroup` 和 `fsGroup`。
- 只挂载目标 PVC，不挂载 ServiceAccount Token。
- 不对外提供 Service。
- 复制完成后立即删除。

复制后至少保存：

- `k8s_inspector.db`
- `k8s_inspector.db-wal` 和 `k8s_inspector.db-shm`（如果存在）
- 文件大小、SHA-256 和备份时间

停止应用后通常不应再有活跃 WAL。若存在，必须连同主库一起备份。

```bash
sha256sum k8s_inspector.db*
```

### 3.3 备份安全配置

单独备份并验证以下内容可以恢复：

- `CONFIG_ENCRYPTION_KEY`
- `SESSION_SECRET`
- 管理员用户名和密码哈希
- 当前 LLM API Key 的来源
- 飞书和通用 Webhook 配置的来源
- TLS/Ingress 配置

`CONFIG_ENCRYPTION_KEY` 丢失后，迁移后的 LLM API Key、Webhook 和签名密钥无法解密。不要在工单、聊天或普通日志中粘贴这些值。

## 4. 预演 migration

在隔离环境中复制一份 v1.0.0 数据库，使用将要发布的 v1.1.0 镜像和同一份配置加密密钥执行：

```bash
python -m app.db.migrate current
python -m app.db.migrate upgrade
python -m app.db.migrate current
```

成功后的 revision 必须是：

```text
v110_platform
```

验证项目：

1. v1.0.0 的模板、白名单、关键字、保存目标和巡检历史仍可读取。
2. 原有 LLM API Key 已加密，API 只返回是否已配置或脱敏状态。
3. 新增表存在，外键检查无异常。
4. 用 v1.1.0 应用访问预演数据库时 `/health/ready` 正常。

建议对数据库执行：

```bash
sqlite3 k8s_inspector.db 'PRAGMA integrity_check;'
sqlite3 k8s_inspector.db 'PRAGMA foreign_key_check;'
```

第一条必须返回 `ok`，第二条应无输出。

如果预演失败，不得在生产环境继续升级。

## 5. 执行升级

### 5.1 准备生产 values

至少确认：

```yaml
replicaCount: 1

image:
  tag: v1.1.0

env:
  appEnv: production
  providerMode: kubernetes
  authMode: local
  sessionCookieSecure: true
  trustedDetailBaseUrl: https://inspector.example.com
  webhookAllowedHosts:
    - open.feishu.cn

secretEnv:
  adminUsername: admin
  adminPasswordHash: replace-with-argon2-hash
  sessionSecret: replace-with-random-secret
  configEncryptionKey: replace-with-existing-or-new-fernet-key
```

不要使用 `--set` 在命令行传递密码和密钥，避免进入 shell history 或进程列表。

### 5.2 升级 release

```bash
helm upgrade RELEASE ./deploy/helm/k8s-inspector \
  -n NAMESPACE \
  -f /secure/path/values-v1.1.0.yaml \
  --atomic \
  --timeout 15m
```

持久化开启时，Chart 的 init container 会在主应用启动前运行：

```text
python -m app.db.migrate upgrade
```

migration 失败时主容器不得启动。注意：`helm --atomic` 能回退 Kubernetes 对象，但不能自动恢复已迁移的 SQLite 内容，因此数据库备份仍是必需品。

## 6. 升级后验收

### 6.0 RBAC 权限预检

v1.1.0 的 Service 和 Ingress 链路巡检需要读取 EndpointSlice，日志巡检需要读取
Pod 日志。升级镜像时必须同步升级 Helm Chart，不能只替换 Deployment 镜像。

```bash
SERVICE_ACCOUNT=system:serviceaccount:k8s-inspector:k8s-inspector-k8s-inspector
TARGET_NAMESPACE=platform

kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as="${SERVICE_ACCOUNT}" \
  -n "${TARGET_NAMESPACE}"

kubectl auth can-i get pods \
  --subresource=log \
  --as="${SERVICE_ACCOUNT}" \
  -n "${TARGET_NAMESPACE}"
```

两条命令都必须返回 `yes`。若 EndpointSlice 返回 `no`，重新执行 5.2 节的
`helm upgrade`，并确认使用的是本版本仓库中的 Chart。仓库默认 ClusterRole
已经包含：

```yaml
- apiGroups: ["discovery.k8s.io"]
  resources: ["endpointslices"]
  verbs: ["get", "list"]
```

### 6.1 Pod 与 migration

```bash
kubectl get pod -n NAMESPACE \
  -l app.kubernetes.io/instance=RELEASE
kubectl logs -n NAMESPACE POD_NAME -c database-migration
kubectl describe pod -n NAMESPACE POD_NAME
```

确认 init container 成功，应用只有一个副本且 Ready。

### 6.2 健康与登录

通过受控的 port-forward 或正式 HTTPS 地址检查：

```bash
curl -fsS https://inspector.example.com/health/live
curl -fsS https://inspector.example.com/health/ready
```

然后在浏览器验证：

1. 未登录不能访问受保护页面和 API。
2. 管理员可以登录、退出，退出后原 Session 立即失效。
3. 系统状态显示数据库、Kubernetes API、Kubernetes 版本、调度器和最近巡检。
4. 手动运行一个小范围巡检，问题、检查覆盖和时间线可查看。
5. 创建一个禁用状态的测试计划，再手动执行。
6. 配置测试飞书群机器人，执行“测试通知”，确认消息有测试标识且不创建 Issue。
7. API 和页面不显示完整 Webhook、签名密钥、Token、密码和原始 Pod 日志。

### 6.3 数据完整性

在不直接输出敏感字段的前提下确认：

- v1.0.0 的模板、白名单、关键字、保存目标和历史数量符合升级前记录。
- migration revision 为 `v110_platform`。
- SQLite `integrity_check` 为 `ok`，`foreign_key_check` 无输出。
- 新建问题、计划和通知投递能持久化，应用重启后仍可读取。

## 7. 回退

### 7.1 何时回退

出现以下任一情况应停止使用新版本并评估回退：

- migration 失败或数据库完整性检查失败。
- 生产安全配置无法通过就绪检查。
- 核心巡检、登录或问题工作台不可用。
- 发现敏感数据泄漏。
- Kubernetes API 负载或日志读取量超出批准范围。

### 7.2 回退原则

推荐恢复升级前数据库快照，不推荐仅执行 Alembic downgrade：

- v1.1.0 会加密原有 LLM API Key，v1.0.0 不能直接使用该密文。
- Alembic downgrade 会删除 v1.1.0 新表及其中数据。
- Helm 回退镜像不会自动回退 SQLite。

回退期间产生的 v1.1.0 问题、计划、通知和审计数据会丢失，应先按安全要求保留故障证据，但不得导出原始日志或密钥。

### 7.3 回退步骤

1. 将 v1.1.0 Deployment 缩容到 0，确认没有进程挂载数据库。
2. 对当前失败状态再做一次隔离备份，供故障分析。
3. 恢复升级前 PVC 快照，或恢复完整的 SQLite 主库、WAL 和 SHM 文件集合。
4. 恢复 v1.0.0 镜像、Chart 和 values。
5. 恢复 v1.0.0 使用的安全配置。
6. 启动一个副本，验证旧数据、健康接口和基础巡检。

Helm 对象可按已记录的 revision 回退：

```bash
helm history RELEASE -n NAMESPACE
helm rollback RELEASE REVISION -n NAMESPACE --wait --timeout 15m
```

必须先完成数据库恢复，或确保回退流程明确包含数据库恢复。不能把 `helm rollback` 当作完整的数据回退。

## 8. 失败处理记录

每次升级或回退至少记录：

- 操作人、开始和结束时间
- 原版本、目标版本、镜像摘要和 Chart 版本
- 数据库备份或快照 ID、SHA-256
- migration 前后 revision
- 健康、登录、数据完整性和巡检验证结果
- 回退决定、原因和数据损失范围

任何备份、日志和截图都必须先检查是否包含密码、Token、Webhook、Session、Secret 或原始 Pod 日志。

# K8s Inspector

K8s Inspector v1.1.0 是面向单个 Kubernetes 集群的只读巡检与排障系统。它将资源状态、对象关系、事件、受限日志证据和问题生命周期集中到一个工作台，帮助运维人员更快定位问题，但不会自动修改集群资源。

## v1.1.0 能力

- 巡检 Deployment、StatefulSet、DaemonSet、Job、CronJob、Pod、Service、EndpointSlice、Ingress、PVC、PV、Node 和可选 Metrics API。
- 区分正常、异常、跳过和采集失败；采集失败不会显示为健康。
- 按指纹合并重复问题，记录开放、升级、确认和恢复时间线。
- 支持手动巡检和单进程定时计划，执行记录保存 API 调用量、日志读取量和耗时。
- 支持飞书群机器人 V2 Webhook 和通用 Webhook 告警，包含签名、失败重试、消息裁剪和目标访问控制。
- 支持本地单管理员登录、服务端 Session、CSRF、登录限流和安全审计。
- 使用 Alembic 将 v1.0.0 SQLite 数据库升级到 v1.1.0。
- 提供 `/health/live`、`/health/ready` 和系统状态页面。

飞书范围仅包括告警通知，不需要 App ID 或 App Secret，也不包含飞书应用机器人、消息接收、卡片按钮回调和远程操作。

## 目录

```text
frontend/                     React + Vite + TypeScript
backend/                      FastAPI + SQLite + Provider
deploy/helm/k8s-inspector/    单副本 Helm Chart
deploy/kk/                    Kubernetes E2E 配置
docs/v1.1.0/                 PRD、架构、验收和升级文档
examples/                     模板与白名单示例
```

## 本地开发

安装并启动后端：

```bash
cd backend
python3 -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

安装并启动前端：

```bash
cd frontend
npm ci
npm run dev
```

本地默认使用 Mock Provider 且关闭鉴权。连接开发集群时只使用只读凭据：

```bash
K8S_PROVIDER_MODE=kubernetes \
KUBECONFIG_PATH=/path/to/kubeconfig \
KUBECONTEXT=your-context \
uvicorn app.main:app --reload
```

系统不会创建、更新、删除集群资源，也不使用 Pod exec。

## 测试与构建

```bash
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
helm lint deploy/helm/k8s-inspector \
  -f deploy/helm/k8s-inspector/ci-values.yaml
```

CI 还配置了 Kubernetes 1.34 和 1.36 的 KubeKey 单节点 E2E。支持范围以这两个边界版本的实际 E2E 结果为准。

## 生产部署

v1.1.0 使用 SQLite 和进程内调度器，只支持一个应用副本。Chart 会拒绝 `replicaCount` 不等于 `1` 的部署。

> 必须使用与镜像相同版本的完整 Helm Chart 部署。禁止只修改 Deployment
> 镜像而不执行 Helm upgrade，否则应用能力与 ServiceAccount RBAC 可能不一致，
> 巡检会出现 `Forbidden`。

部署前至少准备：

- Argon2 管理员密码哈希。
- 长度不少于 32 个字符的 Session Secret。
- Fernet 格式的配置加密密钥。
- HTTPS 访问地址和可信详情页基础地址。
- Webhook 目标主机或 CIDR 允许列表。
- 生产可用的 PVC、镜像标签和只读 ServiceAccount/RBAC。

部署前先确认 Kubernetes 服务端版本：

```bash
kubectl version
```

v1.1.0 当前经过验证的 Kubernetes 范围是 1.34 至 1.36。目标集群不在该范围时，
不能直接作为商用环境部署，应先完成该版本的兼容性验证。

可用以下命令生成随机密钥：

```bash
openssl rand -hex 32
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
python3 -c 'from getpass import getpass; from argon2 import PasswordHasher; print(PasswordHasher().hash(getpass("管理员密码：")))'
```

第三条命令会交互读取管理员密码并输出 Argon2 哈希。不能把明文密码写入 values、命令历史或 Git。敏感值应放入受访问控制的私有 values 文件或由部署平台安全注入。

生产 values 的关键配置示例：

```yaml
replicaCount: 1

image:
  repository: ghcr.io/your-org/k8s-inspector
  tag: v1.1.0

env:
  appEnv: production
  clusterId: production-cluster
  providerMode: kubernetes
  authMode: local
  sessionCookieSecure: true
  trustedDetailBaseUrl: https://inspector.example.com
  webhookAllowedHosts:
    - open.feishu.cn

secretEnv:
  adminUsername: admin
  adminPasswordHash: replace-with-argon2-hash
  sessionSecret: replace-with-at-least-32-random-characters
  configEncryptionKey: replace-with-fernet-key
```

`env.clusterId` 只作为首次初始化系统配置的默认集群标识。系统启动后可在“系统设置 → 基础配置 → 集群标识”中修改；运行时的问题去重、问题工作台过滤和通知来源以数据库中的系统配置为准，不再长期依赖环境变量。

`secretEnv.adminPasswordHash` 只作为首次初始化管理员密码的默认哈希。登录后可在页面左下角“更改密码”中修改；修改后的密码哈希保存在数据库中，后续登录以数据库中的密码哈希为准。

部署：

```bash
helm lint ./deploy/helm/k8s-inspector \
  -f /secure/path/values-production.yaml

helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace \
  -f /secure/path/values-production.yaml \
  --atomic \
  --timeout 15m
```

Chart 默认：

- 使用 `K8S_PROVIDER_MODE=kubernetes` 和集群内 ServiceAccount。
- 创建只读 RBAC，不授予 `create`、`update`、`patch`、`delete` 或 Pod exec。
- 创建 `ReadWriteOnce` PVC，并将 SQLite 文件保存到 `/data/k8s_inspector.db`。
- 在应用启动前由 init container 执行 migration；迁移失败时应用不会启动。
- 就绪探针访问 `/health/ready`，存活探针访问 `/health/live`。

首次生产部署后应检查：

```bash
kubectl -n k8s-inspector rollout status deployment/k8s-inspector
kubectl -n k8s-inspector get pods
kubectl -n k8s-inspector logs deployment/k8s-inspector -c database-migration
```

如果 Helm release 名称不是 `k8s-inspector`，Deployment 名称以 `helm status` 和 `kubectl get deployment` 的结果为准。

### 部署后 RBAC 验收

以下命令按默认 release、namespace 和 ServiceAccount 名称编写。若部署时修改了名称，
应替换 `AUTH_AS`：

```bash
AUTH_AS=system:serviceaccount:k8s-inspector:k8s-inspector-k8s-inspector
TARGET_NAMESPACE=platform

kubectl auth can-i list pods \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list deployments.apps \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list ingresses.networking.k8s.io \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list persistentvolumeclaims \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i get pods \
  --subresource=log \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
```

这些命令必须全部返回 `yes`。Metrics API 是可选项；安装 Metrics Server 后，还应检查：

```bash
kubectl auth can-i list pods.metrics.k8s.io \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
```

如果出现 `Forbidden`，先确认 Helm 中保存的清单包含完整 RBAC：

```bash
helm get manifest k8s-inspector -n k8s-inspector
kubectl get clusterrole k8s-inspector-k8s-inspector -o yaml
kubectl get clusterrolebinding k8s-inspector-k8s-inspector -o yaml
```

不得把采集失败解释为资源健康，也不应通过增加管理员权限解决。使用当前版本 Chart
重新执行 `helm upgrade`，确保只授予 Chart 中声明的只读权限。

### 部署后 TLS 验收

Ingress 引用的 TLS Secret 必须覆盖实际访问域名。能在浏览器访问不代表 Kubernetes
Secret 一定正确，因为外部负载均衡或网关可能使用另一张证书。

```bash
kubectl get secret TLS_SECRET -n INGRESS_NAMESPACE \
  -o jsonpath='{.data.tls\.crt}' \
  | base64 -d \
  | openssl x509 -noout -subject -ext subjectAltName
```

确认 SAN 包含 Ingress host 或合法的单级通配符域名。

## 子路径部署

后端和前端必须使用同一个路径。构建镜像时：

```bash
docker build \
  --build-arg VITE_BASE_PATH=/inspector \
  -t ghcr.io/your-org/k8s-inspector:v1.1.0 .
```

部署时：

```yaml
basePath: /inspector
```

根路径使用空字符串。反向代理是否剥离前缀必须与 `BASE_PATH` 的配置一致。

## 重要运行边界

- Kubernetes 1.34 至 1.36 是 v1.1.0 计划支持范围；1.33 及以下不承诺商用支持。
- Metrics API 是可选能力，缺失时相应检查显示为 skipped，不影响基础巡检。
- 资源链路检查基于 Kubernetes 对象关系，只能表示“配置链路正常/异常”，不代表真实网络请求成功。
- 日志只用于用户主动巡检、异常对象或模板明确要求的证据，不应默认读取全部正常 Pod。
- 单次日志巡检默认上限为 200 个 Pod，可在“系统配置 → 巡检策略”调整；超过当前上限必须缩小范围。
- 完整 Pod 日志、Secret 数据和 TLS 私钥不得持久化或返回；页面只应展示受限且脱敏的摘要。
- Webhook 失败不会回滚巡检结果；生产环境必须配置目标允许列表。
- 系统不执行自动修复，也不支持多副本写入。

## 数据升级与回退

从 v1.0.0 升级前必须停止写入并备份 SQLite 数据库、当前镜像、values 和所有安全密钥。完整步骤见 [v1.1.0 升级与回退指南](docs/v1.1.0/upgrade-guide.md)。

发布验收状态见 [v1.1.0 验收报告](docs/v1.1.0/acceptance-report.md)。

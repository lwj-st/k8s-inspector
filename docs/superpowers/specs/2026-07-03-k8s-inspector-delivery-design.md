# K8s Inspector 交付与部署设计

## 1. 目标

在现有 `K8s Inspector` 前后端骨架基础上，补齐持续集成、镜像构建和 Kubernetes 部署能力，满足以下目标：

- 使用 `GitHub Actions` 执行 CI
- 使用 `GHCR` 推送镜像
- 使用单镜像交付前端与后端
- 使用 `Helm Chart` 部署到 Kubernetes
- 默认支持域名直接访问
- 预留后续通过 `Kong strip-path` 扩展子路径访问

本次设计重点是最小依赖、单镜像、单 Deployment、可在 K8s 内直接运行。

## 2. 约束与前提

- 代码仓库：`https://github.com/lwj-st/k8s-inspector`
- 镜像仓库：`ghcr.io/lwj-st/k8s-inspector`
- CI 平台：`GitHub Actions`
- K8s 部署方式：`Helm Chart`
- 默认访问方式：域名根路径 `/`
- 后续可扩展 `Kong strip-path`
- 尽量减少运行时依赖，不引入额外 nginx sidecar 或双进程容器

## 3. 交付方案对比

### 3.1 单镜像：前端静态资源打包进后端镜像

这是本次采用方案。

特点：

- CI 中先构建前端静态资源
- 再将前端 `dist` 打入 Python 运行镜像
- 后端进程同时提供 API 与前端页面
- K8s 内只部署一个应用容器

优点：

- 依赖最少
- 部署最简单
- 最符合“默认域名直接访问，后续再扩 Kong strip-path”的要求

缺点：

- 镜像体积大于纯后端镜像
- 静态资源缓存能力不如独立 nginx，但首版可接受

### 3.2 单容器双进程：nginx + uvicorn

不采用。

原因：

- 容器内双进程复杂度更高
- 对当前 MVP 来说收益不大

### 3.3 双镜像：前后端分别部署

不采用。

原因：

- 与“尽量少依赖、最好一个镜像”目标不一致

## 4. 总体交付架构

开发态保持前后端分目录：

- `frontend/`
- `backend/`

运行态合并成一个镜像：

- 前端先构建为静态文件
- 后端镜像中包含：
  - Python 运行时
  - 后端应用代码
  - 前端静态资源构建产物

Kubernetes 中部署：

- 一个 `Deployment`
- 一个 `Service`
- 一个应用容器
- 一个 `Ingress`
- 一组只读 `RBAC`

## 5. 应用运行方式设计

### 5.1 后端同时提供 API 与静态页面

应用需要支持两类路由：

- API：`/api/v1/...`
- 前端静态资源与页面：
  - `/`
  - `/assets/...`
  - 前端路由回退到 `index.html`

### 5.2 访问方式

默认方式：

- `https://your-domain/`

未来扩展方式：

- `https://your-domain/inspector/`

因此应用仍保留：

- `BASE_PATH`

但 Helm 默认值先使用空路径，保证直连域名即可访问。

### 5.3 Kong strip-path 扩展位

后续若接入 Kong：

- Ingress 或路由配置为 `/inspector`
- Kong 打开 `strip-path`
- 应用侧可继续通过 `BASE_PATH` 做兼容

首版部署不强制依赖 Kong。

## 6. CI 设计

本次建议拆为两个 workflow。

### 6.1 `ci.yml`

触发条件：

- `pull_request`
- `push` 到 `main`

执行内容：

- 前端安装依赖：`npm ci`
- 前端测试：`npm test -- --run`
- 前端构建：`npm run build`
- 后端安装依赖
- 后端测试：`pytest -v`
- Helm lint

目标：

- 验证代码、测试、前端构建、Chart 基本合法性
- 不推镜像

### 6.2 `release-image.yml`

触发条件：

- `push` 到 `main`
- `push` tag，例如 `v1.0.0`

执行内容：

- 构建前端静态资源
- 构建单镜像
- 登录 `GHCR`
- 推送镜像标签

镜像标签策略：

- `main` 分支：
  - `latest`
  - `main-<sha>`
- `tag`：
  - `vX.Y.Z`

## 7. 镜像构建设计

### 7.1 构建流程

使用单个 `Dockerfile` 的多阶段构建：

第一阶段：

- 使用 Node 镜像
- 构建前端
- 产出 `frontend/dist`

第二阶段：

- 使用 Python 运行时镜像
- 安装后端依赖
- 复制后端代码
- 复制前端 `dist`

最终镜像只包含运行所需文件。

### 7.2 运行命令

镜像默认以单进程启动：

- `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 7.3 运行时环境变量

需要支持：

- `BASE_PATH`
- `K8S_PROVIDER_MODE`
- `K8S_REQUEST_TIMEOUT`
- `LLM_ENABLED`
- `LLM_PROVIDER`
- `MODEL_ENDPOINT`
- `API_KEY`

K8s 内默认采用：

- `K8S_PROVIDER_MODE=kubernetes`

## 8. Kubernetes 访问方式设计

### 8.1 集群内访问 Kubernetes API

部署到 K8s 后，应用默认应优先使用 `in-cluster config`。

这意味着：

- 不依赖外部 kubeconfig 文件
- 使用 Pod 绑定的 `ServiceAccount`
- 使用只读 RBAC

开发环境仍保留外部 kubeconfig 模式，用于本地调试。

### 8.2 读取范围

当前只读访问包括：

- `Node`
- `Namespace`
- `Pod`
- `Service`
- `Ingress`
- `Secret`
- `DaemonSet`
- `Event`
- `Pod Log`

### 8.3 权限边界

Chart 必须只授予读取权限，不允许写操作：

- `get`
- `list`
- `watch`

不授予：

- `create`
- `update`
- `patch`
- `delete`

## 9. Helm Chart 设计

建议目录：

```text
deploy/helm/k8s-inspector/
  Chart.yaml
  values.yaml
  templates/
    deployment.yaml
    service.yaml
    ingress.yaml
    configmap.yaml
    secret.yaml
    serviceaccount.yaml
    clusterrole.yaml
    clusterrolebinding.yaml
```

### 9.1 `values.yaml`

核心配置建议包括：

- `image.repository`
- `image.tag`
- `image.pullPolicy`
- `service.type`
- `service.port`
- `ingress.enabled`
- `ingress.className`
- `ingress.host`
- `ingress.path`
- `basePath`
- `providerMode`
- `resources`
- `env`
- `nodeSelector`
- `tolerations`
- `affinity`

### 9.2 Ingress 默认值

默认值应面向域名根路径：

- `ingress.path: /`
- `basePath: ""`

未来接 Kong 时，允许通过 values 覆盖：

- `ingress.path: /inspector`
- `basePath: /inspector`

### 9.3 Secret 与 ConfigMap

建议拆分：

- 非敏感配置进入 `ConfigMap`
- `API_KEY` 等敏感配置进入 `Secret`

## 10. 代码改造要求

为支持单镜像与 K8s 部署，应用需要补充以下改造：

- 后端支持挂载前端静态资源目录
- 前端构建产物可被后端直接服务
- 后端在 K8s 环境支持 `in-cluster config`
- 保持本地开发和测试模式不被破坏

## 11. 验证要求

CI/CD 与部署完成后至少验证：

- 前端测试通过
- 前端构建通过
- 后端测试通过
- Docker 镜像可构建
- Helm lint 通过
- K8s 中应用可启动
- 域名根路径可访问前端页面
- `/api/v1/...` 可访问
- 应用在集群内可只读访问 Kubernetes API

## 12. 风险与注意事项

- 单镜像方案的核心风险在于静态资源托管与前端路由回退处理
- `BASE_PATH`、Ingress 路径、前端资源路径必须保持一致
- 集群内访问需要严格控制 RBAC，否则容易越权
- 运行时若默认启用 Kubernetes provider，需要确保应用启动时能拿到正确权限

## 13. 结论

本次交付与部署采用：

- `GitHub Actions`
- `GHCR`
- 单镜像
- `Helm Chart`
- K8s 内 `in-cluster` 只读访问

默认支持域名直接访问，后续再扩展 `Kong strip-path`。该方案在当前阶段复杂度最低、依赖最少，也最符合当前产品落地目标。

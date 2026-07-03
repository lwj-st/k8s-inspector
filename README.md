# K8s Inspector

一个面向单集群场景的 K8s 故障排查系统首版骨架，包含：

- `frontend/`：React + Vite + TypeScript 页面骨架
- `backend/`：FastAPI + SQLite + Mock Provider API 骨架
- `examples/`：模板与白名单导入样例

## 目录

```text
frontend/
backend/
examples/
docs/
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

## 前端测试

```bash
cd frontend
npm test -- --run
```

## 后端启动

先安装依赖：

```bash
cd backend
python3 -m pip install -e .[dev]
```

再启动服务：

```bash
uvicorn app.main:app --reload
```

使用真实开发集群只读采集时：

```bash
K8S_PROVIDER_MODE=kubernetes \
KUBECONFIG_PATH=/Users/liwenjian1.vendor/.kube/config_A100_dev \
KUBECONTEXT=kubernetes-admin@kubernetes \
uvicorn app.main:app --reload
```

说明：

- 只会执行读取类 API 调用，不会创建、更新、删除任何集群资源
- 当前实现主要读取 `Node / Namespace / Pod / Service / Ingress / Secret / DaemonSet / Event / Pod Log`

## 后端测试

```bash
cd backend
pytest -v
```

## BASE_PATH 配置

系统支持根路径和子路径访问：

- 根路径：`BASE_PATH=`
- 子路径：`BASE_PATH=/inspector`

前端：

```bash
VITE_BASE_PATH=/inspector npm run dev
```

后端：

```bash
BASE_PATH=/inspector uvicorn app.main:app --reload
```

如果同时接真实集群：

```bash
BASE_PATH=/inspector \
K8S_PROVIDER_MODE=kubernetes \
KUBECONFIG_PATH=/Users/liwenjian1.vendor/.kube/config_A100_dev \
KUBECONTEXT=kubernetes-admin@kubernetes \
uvicorn app.main:app --reload
```

如果前端已构建完成，后端会自动托管 `frontend/dist`，也可以显式指定：

```bash
FRONTEND_DIST_PATH=/absolute/path/to/frontend/dist uvicorn app.main:app --reload
```

## 当前实现边界

- 已实现页面骨架、API 骨架、SQLite 模型、Mock 巡检与排查逻辑
- 已支持切换到 Kubernetes 只读 provider
- 已支持 `BASE_PATH` 前缀配置
- 已支持单镜像部署时由 FastAPI 直接提供前端静态资源
- 默认仍使用 mock provider，只有显式配置后才接真实 Kubernetes
- 当前未实现登录鉴权和自动修复

## Docker 单镜像构建

默认构建根路径版本：

```bash
docker build -t ghcr.io/lwj-st/k8s-inspector:local .
```

如果要为子路径访问构建前端静态资源：

```bash
docker build --build-arg VITE_BASE_PATH=/inspector -t ghcr.io/lwj-st/k8s-inspector:local .
```

运行：

```bash
docker run --rm -p 8000:8000 ghcr.io/lwj-st/k8s-inspector:local
```

## GitHub Actions

- `/.github/workflows/ci.yml`：前端测试、前端构建、后端测试、Helm lint
- `/.github/workflows/ci.yml`：同时包含 `kk` 单节点临时集群 E2E，流程为“建集群 -> 导入镜像 -> Helm 部署 -> `port-forward` 验证 -> `helm test`”
- `/.github/workflows/release-image.yml`：推送 `main` 或版本 tag 时构建并推送 GHCR 镜像

镜像标签策略：

- `main` 分支推送：`latest`、`main-<sha>`
- `vX.Y.Z` tag 推送：`vX.Y.Z`

## Helm 部署

根路径访问：

```bash
helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace \
  --set ingress.hosts[0].host=k8s-inspector.example.com
```

子路径访问预留给后续 Kong `strip-path`：

```bash
helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace \
  --set basePath=/inspector \
  --set ingress.hosts[0].host=k8s-inspector.example.com \
  --set ingress.hosts[0].paths[0].path=/inspector \
  --set ingress.annotations."konghq\.com/strip-path"=true
```

说明：

- K8s 内默认 `K8S_PROVIDER_MODE=kubernetes`
- 默认 `PREFER_INCLUSTER=true`，优先使用 Pod `ServiceAccount`
- Chart 会创建只读 `RBAC`，不会授予写权限
- Chart 默认把 `DATABASE_URL` 设为 `sqlite:////tmp/k8s_inspector.db`，避免非 root 容器写工作目录失败
- 当前 CI 的 E2E 不依赖域名，也不启用 `Kong strip-path`；相关 `basePath` 和 Ingress 配置仍保留，后续可直接扩展

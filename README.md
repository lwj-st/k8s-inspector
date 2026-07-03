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

## 当前实现边界

- 已实现页面骨架、API 骨架、SQLite 模型、Mock 巡检与排查逻辑
- 已支持切换到 Kubernetes 只读 provider
- 已支持 `BASE_PATH` 前缀配置
- 默认仍使用 mock provider，只有显式配置后才接真实 Kubernetes
- 当前未实现登录鉴权和自动修复

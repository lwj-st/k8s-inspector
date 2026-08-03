# K8s Inspector v1.2.0 验收报告

## 状态

当前为代码侧验收记录。本文只记录本地实际执行结果，不记录未执行的真实集群结论。

## 本切片范围

- 页面文案降噪、浅色主题、左侧导航和用户菜单。
- 问题工作台默认开放问题、问题详情聚焦定位。
- 状态巡检、日志巡检、模板检查和名称空间证据抽屉展示收敛。
- 根路径和 `/inspector/` 子路径部署兼容。
- 前端路由、API base URL、刷新前端路由、通知详情链接使用 `basePath`。
- Helm values 提供根路径和子路径示例，渲染时健康探针和 Ingress path 与 `basePath` 一致。
- 后端覆盖问题恢复、已忽略恢复、设置 `cluster_id` 生效、通知详情链接、API 字段兼容。

## 已执行测试

- 后端完整测试：`python3 -m pytest -q backend/tests`
  - 结果：通过，`380 passed, 1 warning`
  - warning：现有 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`
- 前端完整测试：`cd frontend && npm test -- --run`
  - 结果：通过，`14 passed` 文件，`94 passed` 用例
- 前端构建：`cd frontend && npm run build`
  - 结果：通过
- Helm 根路径 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-root.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 子路径 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-subpath.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 根路径渲染：`helm template k8s-inspector deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-root.yaml`
  - 结果：通过
  - 关键渲染：`BASE_PATH: ""`，Ingress path `/`，readiness `/health/ready`，liveness `/health/live`，Helm test URL `/api/v1/system/status`
- Helm 子路径渲染：`helm template k8s-inspector deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-subpath.yaml`
  - 结果：通过
  - 关键渲染：`BASE_PATH: "/inspector"`，Ingress path `/inspector`，readiness `/inspector/health/ready`，liveness `/inspector/health/live`，Helm test URL `/inspector/api/v1/system/status`

## 文案扫描

- `frontend/src`、`README.md`、`deploy/helm/k8s-inspector` 和 `backend/app` 中未发现 PRD 指定的默认页面无效文案残留。
- `frontend/src` 中只保留测试里的“不应出现”断言文本。

## 未执行测试

- 真实 Kubernetes 1.34/1.36 集群 E2E：本切片未连接真实集群，不能给出真实集群通过结论。
- 浏览器 1366px/390px 人工截图验收：本地单元测试覆盖了响应式和主题断言，但未连接真实部署页面人工截图验收。

## 风险

- 同一个实例同时支持 `/` 和 `/inspector/` 双入口不在 v1.2.0 P0 范围内。
- 网关剥离路径时必须把应用按根路径部署；默认 Helm 配置按“不剥离前缀”处理。

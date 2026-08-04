# K8s Inspector v1.2.0 验收报告

## 状态

当前为代码侧验收记录。本文只记录本地实际执行结果，不记录未执行的真实集群结论。

## 需求口径说明

PRD 与用户后续口述需求冲突时，以用户最新口述需求为准。本轮已同步更新 PRD：模板检查全部未命中时不展示额外空提示。

## 本切片范围

- 页面文案降噪、浅色主题、左侧导航和用户菜单。
- 问题工作台默认开放问题、问题详情聚焦定位。
- 问题批量确认、批量忽略、批量恢复显示。
- 问题详情处理记录、证据筛选、单问题 Markdown 复制和下载。
- 问题工作台自动刷新开关和刷新间隔配置。
- 维护静默窗口配置、通知抑制、生命周期记录和静默结束后一次性摘要。
- 状态巡检、日志巡检、模板检查和名称空间证据抽屉展示收敛；模板检查全部未命中时不展示额外空提示。
- 根路径、`/inspector/` 子路径和同实例双入口部署兼容。
- 前端路由、API base URL、刷新前端路由、通知详情链接使用 `basePath`。
- Helm values 提供根路径、子路径和同实例双入口示例，渲染时健康探针和 Ingress path 与部署方式一致。
- 后端覆盖问题恢复、已忽略恢复、设置 `cluster_id` 生效、通知详情链接、API 字段兼容。

## 已执行测试

- 后端完整测试：`python3 -m pytest -q backend/tests`
  - 结果：通过，`385 passed, 1 warning`
  - warning：现有 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`
- 前端完整测试：`cd frontend && npm test -- --run`
  - 结果：通过，`14 passed` 文件，`98 passed` 用例
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
- Helm 双入口 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-dual.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 三形态渲染脚本：`deploy/helm/k8s-inspector/test-template.sh`
  - 结果：通过，输出 `ok root`、`ok subpath`、`ok dual`
  - 关键渲染：双入口模式 `BASE_PATH: ""`，主 Ingress path `/`，额外 Ingress path `/inspector`，readiness `/health/ready`

## 文案扫描

- `frontend/src`、`README.md`、`deploy/helm/k8s-inspector` 和 `backend/app` 中未发现 PRD 指定的默认页面无效文案残留。
- `frontend/src` 中只保留测试里的“不应出现”断言文本。

## 未执行测试

- 真实 Kubernetes 1.34/1.36 集群 E2E：本切片未连接真实集群，不能给出真实集群通过结论。
- 浏览器 1366px/390px 人工截图验收：本地单元测试覆盖了响应式和主题断言，但未连接真实部署页面人工截图验收。

## 风险

- 同实例双入口依赖网关对 `/inspector` 执行 rewrite/strip path；不剥离前缀时必须使用子路径部署。
- 子路径部署和双入口部署不能混用同一套 path 处理规则，部署前必须确认网关行为。

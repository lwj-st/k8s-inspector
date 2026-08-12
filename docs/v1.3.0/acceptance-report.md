# K8s Inspector v1.3.0 验收报告

## 状态

当前为 v1.3.0 发布前代码侧验收记录。本文只记录本地实际执行结果，不记录未执行的真实集群结论。

## 本版本范围

- 日志巡检支持默认最近 15 分钟、快捷时间范围和自定义起止时间。
- 日志记录从“日志巡检”发起，在“日志记录”页面查看、停止和管理。
- 日志记录支持多名称空间单任务、长期保存、改名、备注、删除、分页和名称空间筛选。
- 日志记录详情支持按 Pod/容器查看、折叠视图、原始逐行、搜索高亮、模板匹配和日志下载。
- 日志入库前脱敏，导出和模板匹配使用脱敏后的日志。
- 重复日志按指纹折叠，记录和 Pod 字节上限触发截断或自动停止。
- 系统设置新增日志记录策略和日志巡检最大时间范围配置。
- README、截图、Helm Chart 版本和发布示例已按 `v1.3.0` 收口。

## 已执行测试

- 后端完整测试：`python3 -m pytest -q backend/tests`
  - 结果：通过，`410 passed, 2 warnings`
  - warnings：
    - `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`
    - `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning
- 前端完整测试：`cd frontend && npm test -- --run`
  - 结果：通过，`15 passed` 文件，`105 passed` 用例
  - warning：Node 输出 `--localstorage-file was provided without a valid path`
- 前端构建：`cd frontend && npm run build`
  - 结果：通过
  - warning：Vite chunk size 超过 500 kB 提示
- Helm 根路径 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-root.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 子路径 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-subpath.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 双入口 lint：`helm lint deploy/helm/k8s-inspector -f deploy/helm/k8s-inspector/ci-values.yaml -f deploy/helm/k8s-inspector/values-dual.yaml`
  - 结果：通过，`1 chart(s) linted, 0 chart(s) failed`
- Helm 三形态渲染脚本：`deploy/helm/k8s-inspector/test-template.sh`
  - 结果：通过，输出 `ok root`、`ok subpath`、`ok dual`

## 文档检查

- README 主截图已更新为问题工作台、日志巡检、日志记录和系统设置。
- README 日志记录流程已对齐当前设计：日志巡检页发起，日志记录页查看和停止。
- README 和 Helm README 中镜像示例使用 `ghcr.io/lwj-st/k8s-inspector:v1.3.0`。
- Helm Chart `version` 为 `1.3.0`，`appVersion` 为 `v1.3.0`。

## 未执行测试

- 真实 Kubernetes 1.34/1.36 集群 E2E：本次未连接真实集群，不能给出真实集群通过结论。
- 真实 namespace 日志记录验证：本次未连接真实集群，不能确认 Kubernetes Provider 在真实集群下的端到端日志记录表现。
- 浏览器人工截图验收：本次未执行真实浏览器人工验收。

## 风险

- GitHub Actions 发布镜像依赖打 `v1.3.0` tag；无 `v` 的 `1.3.0` tag 不触发现有 release workflow。
- 同实例双入口依赖网关对 `/inspector` 执行 rewrite/strip path；不剥离前缀时必须使用子路径部署。
- SQLite 和进程内调度器只支持单副本部署，生产环境必须保持 `replicaCount: 1`。

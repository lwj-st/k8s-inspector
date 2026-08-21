# K8s Inspector v1.4.0 验收报告

## 状态

当前为 v1.4.0 开发中的代码侧阶段性验收记录，尚未代表正式发布。本文只记录本地实际执行结果，不记录未执行的真实集群结论。

## 本版本范围

- 新增“镜像清单”页面和左侧导航入口。
- 支持选择一个或多个名称空间后查询镜像；未选择名称空间时不查询全集群。
- 镜像主列表和导出覆盖 Pod spec 中的初始化容器、运行容器；Pod status 中的 `image` 和 `imageID` 只作为详情辅助字段展示。
- 镜像按首尾空格裁剪后的地址去重，不猜测默认 registry，不改写 tag 或 digest。
- 主列表展示镜像、名称空间数、Pod 数、容器数、最近 Pod 创建时间和最近 Pod 状态。
- 详情展示名称空间、Pod、Pod 阶段、容器、容器类型、来源、imageID 和 Pod 创建时间。
- 支持按镜像关键字搜索，支持导出当前筛选结果为 `.txt`；导出文件只包含 Pod spec 镜像地址，每行一个，不包含 `status.image` 或 `imageID/@sha256` 运行时镜像 ID。
- Mock Provider 提供稳定镜像数据，覆盖 init container、运行容器、Succeeded Pod 和 imageID。

## 已执行测试

- 后端目标测试：`python3 -m pytest -q backend/tests/test_image_inventory_api.py backend/tests/test_image_inventory_service.py`
  - 结果：通过，`8 passed, 2 warnings`
  - warnings：
    - `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`
    - `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning
- 后端完整测试：`python3 -m pytest -q backend/tests`
  - 结果：通过，`419 passed, 3 warnings`
- 前端目标测试：`cd frontend && npm test -- --run src/pages/ImageInventoryPage.test.tsx src/app/App.test.tsx`
  - 结果：通过，`12 passed`
- 前端完整测试：`cd frontend && npm test -- --run`
  - 结果：通过，`16 passed` 文件，`109 passed` 用例
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

## 未执行测试

- 真实 Kubernetes Provider 端到端验证：本轮未连接真实集群。
- 真实包含初始化容器和已完成 Pod 的 namespace 人工验收：本轮未执行。

## 运行边界

- 镜像清单只来自 Kubernetes API 当前可见 Pod 的 spec/status 引用。
- 主列表和 TXT 导出只列出 Pod spec 的镜像地址，不列出 `status.image` 或 `imageID/@sha256` 运行时镜像 ID。
- 系统不读取节点本地镜像缓存，不接入镜像仓库，不拉取镜像，不扫描漏洞。
- 已删除且 Kubernetes API 不可见的 Pod 不会被统计。
- `imageID` 是否存在取决于 Kubernetes 运行时和当前 Pod 状态。

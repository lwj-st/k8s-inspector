# 自动巡检切片一验收记录与回修指令

## 1. 验收结论

切片一“自动发现名称空间”已基本完成，但不建议直接进入切片二。需要先做一轮小回修，确保边界符合 `2026-07-12-auto-inspection-slice-1-instructions.md`。

已通过验证：

- `python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_discovery_api.py backend/tests/test_contract_models.py`：17 passed。
- `python3 -m pytest -q backend/tests`：53 passed。
- `cd frontend && npm test -- --run`：23 passed。
- `cd frontend && npm run build`：通过。

## 2. 已完成内容

### 2.1 K8s 采集与证据抽取

已完成：

- provider 抽象新增 `list_namespaces()`。
- Kubernetes provider 已调用 Kubernetes API 发现名称空间。
- Kubernetes provider 已按 namespace 统计 Pod 数和异常 Pod 数。
- provider 测试已覆盖 Kubernetes provider 和 mock provider。

### 2.2 巡检编排与检查入口

已完成：

- 新增 `GET /api/v1/discovery/namespaces`。
- 已在总 router 注册 discovery route。
- API 测试已覆盖基本成功返回。

### 2.3 前端工作台与人性化 UI

已完成：

- 首页已切到自动巡检页。
- 页面自动调用 `discoverNamespaces()`。
- 已支持搜索名称空间。
- 已支持多选。
- 已展示名称空间摘要。
- 主页面没有导入导出 textarea，没有保存巡检对象主流程。

## 3. 发现的问题

### 3.1 Mock provider 数据不符合切片指令

位置：

- `backend/app/providers/mock_provider.py`

问题：

- 切片指令要求 mock provider 至少返回 3 个 namespace，且至少 1 个有异常摘要。
- 当前只返回 1 个 `demo` namespace。

影响：

- 前端和 API 的默认体验不足，不能稳定覆盖搜索、多选、多状态场景。

回修要求：

- mock provider 返回至少 3 个 namespace，例如 `demo`、`prod-core`、`kube-system`。
- 至少一个 `warning`，至少一个 `healthy`。
- 补测试断言 mock provider namespace 数量和状态组合。

### 3.2 Discovery API 缺少 service 边界和排序

位置：

- `backend/app/api/routes/discovery.py`

问题：

- route 直接调用 provider 并返回，没有 service 层。
- 切片指令要求 namespaces 按名称排序，当前未在 API 层保证排序。
- 当前 API 测试只验证第一个 `demo`，没有覆盖排序和空列表。

影响：

- 后续批量巡检和历史状态接入时，route 容易继续膨胀。
- UI 列表顺序依赖 provider 返回顺序，不稳定。

回修要求：

- 新增 `backend/app/services/discovery_service.py`。
- route 只负责依赖注入和调用 service。
- service 负责组装 `NamespaceDiscoveryResponse` 并按 `name` 排序。
- API 测试补充：
  - 成功返回。
  - 空 namespace 列表。
  - 返回结果按 name 排序。

### 3.3 前端 retry 失败会产生未捕获 Promise

位置：

- `frontend/src/pages/AutoInspectionPage.tsx`
- `frontend/src/features/inspections/useDiscoverNamespaces.ts`

问题：

- `refresh()` 在 catch 后重新 `throw reason`。
- 页面重试按钮调用 `void refresh()`，如果重试再次失败，会产生未捕获 Promise。

影响：

- 真实环境 API 失败时，页面虽然能显示错误，但浏览器控制台会有未处理异常，不利于稳定性。

回修要求：

- 二选一：
  - `useDiscoverNamespaces.refresh()` 捕获后不再 rethrow。
  - 或页面按钮调用 `void refresh().catch(() => undefined)`。
- 补前端测试覆盖“首次失败，点击重试仍失败，页面继续显示错误且测试无未处理异常”。

### 3.4 UI 文案仍有英文装饰词

位置：

- `frontend/src/pages/AutoInspectionPage.tsx`

问题：

- eyebrow 使用 `Auto Inspection`。
- 产品纠偏文档要求不使用抽象英文标题。

回修要求：

- 改成中文，例如 `自动发现` 或 `巡检入口`。

## 4. 下一步下发指令

### 4.1 让“K8s 采集与证据抽取”回修

参考本文档第 3.1 节。

只做：

- mock provider 返回至少 3 个 namespace。
- provider 测试补充数量和状态组合。

不要做：

- 批量巡检。
- 日志采集。
- 模板匹配。

### 4.2 让“巡检编排与检查入口”回修

参考本文档第 3.2 节。

只做：

- discovery service。
- discovery route 调 service。
- names 按名称排序。
- API 测试补空列表和排序。

不要做：

- `POST /api/v1/inspections/namespaces/run`。
- 批量巡检。
- 前端页面。

### 4.3 让“前端工作台与人性化 UI”回修

参考本文档第 3.3 和 3.4 节。

只做：

- retry 失败不产生未捕获 Promise。
- eyebrow 改中文。
- 补 retry 失败测试。

不要做：

- 批量巡检交互。
- Pod 详情抽屉。
- 导入导出。
- 保存巡检对象。

## 5. 回修后验收命令

回修完成后必须执行：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_discovery_api.py
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

全部通过后，才进入切片二“选中名称空间并触发巡检”。


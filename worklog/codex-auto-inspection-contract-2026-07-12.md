# Worklog: 自动发现名称空间与批量名称空间巡检契约

## 时间

- 日期：2026-07-12
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`，只完成“自动发现名称空间 + 批量名称空间巡检”的契约层收口，不做 UI、不做 Kubernetes 采集实现、不改导入导出主流程。

## 已完成内容

### 1. 后端共享 schema 已补齐

新增并冻结以下契约：

- `AbnormalCategory`
  - `pod_status`
  - `container_status`
  - `event`
  - `log_keyword`
  - `related_object`
- `NamespaceSummary`
- `NamespaceDiscoveryResponse`
- `NamespaceBatchInspectionRequest`
- `NamespaceBatchInspectionResult`
- `NamespaceBatchInspectionResponse`

关键规则：

- `NamespaceBatchInspectionRequest`
  - `all_namespaces=true` 时允许 `namespaces=[]`
  - `all_namespaces=false` 时必须传至少一个 namespace
- `NamespaceBatchInspectionResponse`
  - 只冻结 `summary + detail_target`
  - 不在批量结果里内联完整 `NamespaceInspectionResponse`

这样做的原因：

- 满足“按名称空间返回巡检摘要和详情引用”
- 不把后续采集实现和详情页结构过早写死

### 2. 前端类型与 API client 已同步

已同步到：

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`

新增前端类型：

- `AbnormalCategory`
- `NamespaceSummary`
- `NamespaceDiscoveryResponse`
- `NamespaceBatchInspectionRequest`
- `NamespaceBatchInspectionResult`
- `NamespaceBatchInspectionResponse`

新增 client 方法：

- `discoverNamespaces()`
- `runNamespaceBatchInspection(payload)`

说明：

- 这里只是为后续切片开发提供稳定调用入口
- 没有新增页面，也没有改现有页面行为

### 3. 契约文档已更新

已更新：

- `docs/superpowers/plans/2026-07-11-api-contract.md`

本轮补充了：

- `AbnormalCategory` 枚举说明
- `NamespaceSummary` 字段冻结
- `NamespaceDiscoveryResponse` 字段冻结
- `NamespaceBatchInspectionRequest` 规则
- `NamespaceBatchInspectionResponse` 结构说明
- 自动发现名称空间和批量巡检主流程不再依赖 `SavedInspectionTarget`

### 4. 最小测试已补齐

已补测试覆盖：

- 名称空间发现摘要字段
- 批量巡检请求校验
- 批量巡检响应结构
- 异常分类非法值拒绝

## 刻意没做的内容

- 没有新增后端 route
- 没有实现 Kubernetes 名称空间自动发现
- 没有实现批量名称空间巡检编排
- 没有改名称空间巡检页面
- 没有改模板、白名单、导入导出主流程

这些内容应由后续切片分别完成。

## 后续切片启动边界

### 后端切片可以开始做

职责：

- 基于本次契约实现 `GET /api/v1/discovery/namespaces`
- 基于本次契约实现 `POST /api/v1/inspections/namespaces/run`
- 编排单名称空间巡检结果，回填批量摘要

边界：

- 不要改 `NamespaceSummary` / `NamespaceBatchInspectionResponse` 字段名
- 不要把 `SavedInspectionTarget` 重新拉回主流程
- 不要在批量结果里擅自内联新的大对象详情

### 前端切片可以开始做

职责：

- 基于 `discoverNamespaces()` 做名称空间自动发现列表
- 基于 `runNamespaceBatchInspection()` 做选中巡检 / 全部巡检入口
- 展示名称空间摘要状态、异常数量、最近巡检时间

边界：

- 不要先做导入导出主流程
- 不要自己推断异常分类
- 不要前端伪造批量巡检详情结构

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
```

结果：

- `11 passed, 1 warning`

已执行：

```bash
cd frontend && npm test -- --run
```

结果：

- `7 files passed`
- `20 tests passed`

已执行：

```bash
cd frontend && npm run build
```

结果：

- build 成功

## 当前结论

这轮“自动发现名称空间 + 批量名称空间巡检”契约已经收口完成，可作为后端切片和前端切片的共同边界继续开发。

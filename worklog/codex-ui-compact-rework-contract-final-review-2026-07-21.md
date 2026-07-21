# Worklog: 2026-07-21 UI 大调整第三阶段契约复核

## 时间

- 日期：2026-07-21
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-21-ui-compact-rework-instructions.md` 中“统一契约与数据模型”在第三阶段的最终复核任务，核对：

1. 前端路由和 API 类型没有虚构字段
2. Label Selector discovery 契约前后端一致
3. `InspectionTarget`、`KeywordHit`、`TemplateMatchResult` 没有被 UI 私自改语义
4. 旧路由兼容策略是否明确
5. 测试断言是否已使用新文案

## 已核对文件

1. `frontend/src/api/types.ts`
2. `backend/app/schemas/inspection.py`
3. `backend/app/api/routes/discovery.py`
4. `frontend/src/routes/index.tsx`
5. `frontend/src/layouts/AppLayout.tsx`
6. `frontend/src/pages/OverviewPage.tsx`
7. 切片 21 UI 指令文档

## 复核结论

### 1. API 类型未被 UI 虚构字段污染

当前前端 `types.ts` 中：

1. `InspectionTarget`
2. `KeywordHit`
3. `TemplateMatchResult`
4. `NamespaceLabelDiscoveryResponse`

仍与后端 schema 保持同一套字段语义，没有出现前端为 UI 方便而补造后端不存在字段的情况。

### 2. Label Selector discovery 契约前后端一致

已确认：

1. 后端 schema 存在 `NamespaceLabelDiscoveryResponse`
2. 后端路由存在 `GET /api/v1/discovery/namespaces/{namespace}/labels`
3. 前端 type 存在 `NamespaceLabelDiscoveryResponse`
4. 前端 client 已有 `discoverNamespaceLabels(namespace)`

字段一致：

1. `namespace`
2. `executed_at`
3. `labels[].key`
4. `labels[].values`
5. `labels[].selector`
6. `labels[].pod_count`

### 3. 共享契约语义未被页面私改

已确认：

1. `InspectionTarget` 仍保持共享目标结构
2. `KeywordHit` 仍保持日志命中结构
3. `TemplateMatchResult` 仍保持模板匹配结果结构

本轮 UI 调整没有把这些共享结构改造成页面专用结构。

## 发现的问题

### 问题 1：旧路由兼容策略尚未满足文档要求

文档要求：

- 可保留 `/inspections/pod` 路由兼容旧地址，但必须重定向或复用 `日志巡检` 页面，不再作为独立导航。

当前实际情况：

1. [frontend/src/routes/index.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/routes/index.tsx:19) 仍将 `/inspections/pod` 直接路由到独立的 `PodInspectionPage`
2. [frontend/src/pages/OverviewPage.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/pages/OverviewPage.tsx:70) 仍有“巡检单个 Pod”快速入口直接跳到 `/inspections/pod`

影响：

- 旧地址兼容并未收敛为统一的“日志巡检”页面
- 仍保留了一个事实上的独立 Pod 巡检入口
- 与本轮“日志巡检合并名称空间巡检和单 Pod 巡检能力”的 IA 目标不完全一致

结论：

- 这是当前第三阶段复核里最明确的剩余问题
- 该问题属于前端路由/页面复用策略问题，不是后端契约问题

### 问题 2：旧文案入口仍有残留

当前导航主文案已切换为：

1. `状态巡检`
2. `日志巡检`
3. `模板检查`
4. `故障模板`
5. `关键字库`
6. `系统配置`

但 `OverviewPage` 的快速入口文案仍显示：

1. `巡检名称空间`
2. `巡检单个 Pod`

这会继续强化旧的信息架构概念。

## 测试复核

本轮已启动：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_discovery_api.py
cd frontend && npm test -- --run src/app/App.test.tsx src/routes/basePath.test.tsx src/pages/NamespaceInspectionPage.test.tsx src/pages/PodInspectionPage.test.tsx
```

说明：

- 后端测试用于确认契约和 discovery 结构仍正常
- 前端测试用于确认新导航文案和相关页面没有立即断裂
- 若后续测试结果有额外失败，应由主会话结合失败日志继续判断

## 当前结论

1. 契约层本身没有发现新的字段分裂问题。
2. Label Selector discovery 契约已对齐。
3. 最大剩余问题不是 API，而是前端仍保留 `/inspections/pod` 独立页面和旧入口文案，尚未完全符合 UI 大调整文档里的旧路由兼容策略。

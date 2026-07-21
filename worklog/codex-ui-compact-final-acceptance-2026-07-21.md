# 2026-07-21 UI 大调整最终验收记录

## 验收范围

本次验收覆盖 `docs/superpowers/plans/2026-07-21-ui-compact-rework-review-followup.md` 中的返工项：

1. `状态巡检` 收口为“巡检全部名称空间”或“单选名称空间巡检”。
2. `/inspections/pod` 旧路由复用统一 `日志巡检` 页面。
3. `KeywordHit` 增加日志命中上下文字段。
4. 后端生成命中行上下 5 行上下文。
5. `日志巡检`、`状态巡检` 证据抽屉、`模板检查` 优先展示日志上下文。

## 验收结果

通过。

## 核对结论

### 1. 状态巡检

已确认：

1. 页面顶部提供 `选择名称空间` 下拉框。
2. 主操作为 `巡检该名称空间` 和 `巡检全部名称空间`。
3. 未巡检状态下不再展示完整 `名称空间列表`。
4. 不再存在 `全选当前结果`、`取消当前结果`、`巡检选中`。

### 2. 日志巡检与旧路由

已确认：

1. 导航只展示 `日志巡检`，不展示 `单 Pod 巡检`。
2. `/inspections/namespace` 和 `/inspections/pod` 都复用统一 `NamespaceInspectionPage`。
3. `/inspections/pod` 不再默认进入单 Pod 模式，而是进入统一日志巡检入口。
4. `OverviewPage` 的日志巡检快捷入口指向 `/inspections/namespace`。

### 3. 日志命中上下文

已确认：

1. 后端 `KeywordHit` 增加：
   - `context_before`
   - `context_after`
   - `context_text`
2. 系统关键字和模板显式日志关键字都会生成上下文。
3. 模板 matcher 证据会携带上下文字段。
4. 前端展示优先级为 `context_text -> matched_text`。
5. UI 文案明确为 `命中上下文（不是完整日志）`。

## 已执行验证

```bash
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端：102 passed，1 个既有 Starlette/httpx deprecation warning。
2. 前端测试：54 passed。
3. 前端构建：通过。

## 残余小问题

1. `frontend/src/app/App.test.tsx` 中有一个测试名称仍写着 `renders status inspection home with namespace list`，但断言已经确认页面不显示 `名称空间列表`。这是测试描述命名问题，不影响功能。
2. 页面局部文案仍有 `名称空间巡检入口`，这是状态巡检页面内部说明，不是旧导航入口。如后续继续打磨文案，可改成 `状态巡检入口`。

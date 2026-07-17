# Worklog: 自动巡检页名称空间列表、搜索、多选

## 时间

- 日期：2026-07-12
- Agent：Codex

## 任务范围

本次只完成自动巡检页首屏的名称空间发现结果展示：

1. 名称空间列表
2. 搜索名称空间
3. 多选名称空间

本次不做：

1. 不改后端
2. 不做批量巡检执行
3. 不做 Pod 详情抽屉
4. 不做模板页
5. 不做白名单页
6. 不引入 demo 数据

## 本次完成内容

### 1. 新增自动巡检页

新增文件：

- `frontend/src/pages/AutoInspectionPage.tsx`

页面行为：

1. 进入页面自动调用 `discoverNamespaces()`
2. 首屏展示名称空间搜索框
3. 展示名称空间列表
4. 每个名称空间提供 checkbox
5. 展示已选数量
6. 提供：
   - `全选当前结果`
   - `取消当前结果`
   - `巡检选中（下一切片开放）`
   - `巡检全部（下一切片开放）`

### 2. 新增名称空间发现 hook

新增文件：

- `frontend/src/features/inspections/useDiscoverNamespaces.ts`

作用：

1. 封装 `discoverNamespaces()`
2. 统一处理加载状态
3. 统一处理错误状态
4. 提供重试能力

### 3. 首页切到自动巡检

修改文件：

- `frontend/src/routes/index.tsx`
- `frontend/src/layouts/AppLayout.tsx`

调整结果：

1. 路由首页 `"/"` 改为自动巡检页
2. 左侧导航首项改为 `自动巡检`
3. 保留现有名称空间巡检页和 Pod 巡检页，不动它们的业务逻辑

### 4. 自动巡检页当前展示内容

当前列表展示：

1. 名称空间名称
2. 状态
3. Pod 数
4. 异常 Pod 数
5. 最近巡检时间

空状态：

1. 没有名称空间时显示明确提示
2. 搜索无结果时显示调整搜索条件提示

失败状态：

1. 显示失败原因
2. 提供重试按钮

## 涉及文件

- `frontend/src/features/inspections/useDiscoverNamespaces.ts`
- `frontend/src/pages/AutoInspectionPage.tsx`
- `frontend/src/pages/AutoInspectionPage.test.tsx`
- `frontend/src/routes/index.tsx`
- `frontend/src/layouts/AppLayout.tsx`
- `frontend/src/styles.css`
- `frontend/src/app/App.test.tsx`

## 测试变更

新增：

- `frontend/src/pages/AutoInspectionPage.test.tsx`

覆盖：

1. 加载成功
2. 空列表
3. 失败重试
4. 搜索名称空间
5. 多选名称空间

更新：

- `frontend/src/app/App.test.tsx`

原因：

1. 首页已经从旧工作台切到自动巡检页
2. 测试需要改为校验名称空间发现首页

## 边界说明

1. 本次没有调用批量巡检接口
2. `巡检选中` 和 `巡检全部` 目前按产品文档要求先置灰
3. 本次只消费后端已提供的 `discoverNamespaces()` 契约
4. 本次没有 mock 后端不存在的批量巡检结果

## API 契约影响

本次未改 API 契约。

只消费已有：

1. `NamespaceSummary`
2. `NamespaceDiscoveryResponse`
3. `discoverNamespaces()`

## 当前结论

自动巡检页第一步已经可用：

1. 用户进入首页能看到名称空间列表
2. 可以搜索名称空间
3. 可以多选名称空间
4. 可以清楚看到后续批量巡检入口，但不会误触发未完成能力

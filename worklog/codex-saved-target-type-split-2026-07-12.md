# Worklog: 保存对象类型分流

## 时间

- 日期：2026-07-12
- Agent：Codex

## 任务范围

参考
`docs/superpowers/plans/2026-07-11-agent-development-instructions.md`
第 18 节，只处理保存对象类型分流。

本次不做：

1. 不改后端
2. 不改模板页
3. 不改白名单页
4. 不新增 demo/mock 数据
5. 不改保存对象 schema

## 选择方案

本次选择方案 A。

方案 A 的落地结果：

1. 名称空间巡检页只展示 `target_type === "namespace"` 的保存对象
2. Pod 巡检页只展示 `target_type === "pod"` 的保存对象
3. Pod 巡检页支持保存、使用、编辑、删除、导入、导出 pod 保存对象

## 本次完成内容

### 1. 保存对象 hook 按类型复用

调整文件：

- `frontend/src/features/inspections/useSavedInspectionTargets.ts`

处理方式：

1. `useSavedInspectionTargets()` 改为接收 `targetType`
2. 初始加载时只保留对应类型的保存对象
3. 导出时只导出当前类型对象
4. 导入后只回填当前类型对象
5. 保存和更新时自动写入当前页面对应的 `target_type`

这样做的目的：

- 不改后端接口
- 不改 schema
- 前端就能把 namespace / pod 两类对象清晰分流

### 2. 名称空间巡检页只处理 namespace 保存对象

调整文件：

- `frontend/src/pages/NamespaceInspectionPage.tsx`

结果：

1. 页面调用 `useSavedInspectionTargets("namespace")`
2. 不再展示 pod 类型保存对象
3. 名称空间页里的“使用”按钮只会执行名称空间巡检

### 3. Pod 巡检页补齐 pod 保存对象完整管理

调整文件：

- `frontend/src/pages/PodInspectionPage.tsx`

新增能力：

1. 展示已保存 Pod 巡检对象
2. 保存当前 `namespace + pod_name`
3. 使用保存对象直接运行 Pod 巡检
4. 编辑 Pod 保存对象
5. 删除 Pod 保存对象
6. 导出 Pod 保存对象
7. 导入 Pod 保存对象

页面上的对象字段现在明确是：

1. 名称空间
2. Pod 名称
3. 保存名称

## namespace / pod 两类保存对象分别在哪个页面使用

### namespace 保存对象

展示和使用页面：

- `NamespaceInspectionPage`

用途：

- 运行名称空间巡检
- 保存 `namespace + label_selector`

### pod 保存对象

展示和使用页面：

- `PodInspectionPage`

用途：

- 运行 Pod 巡检
- 保存 `namespace + pod_name`

## 测试变更

### 名称空间页

更新：

- `frontend/src/pages/NamespaceInspectionPage.test.tsx`

新增覆盖：

1. 名称空间页不会展示 pod 类型保存对象的“使用”按钮
2. 原有 namespace 保存对象相关测试继续通过

### Pod 页

更新：

- `frontend/src/pages/PodInspectionPage.test.tsx`

新增覆盖：

1. Pod 页只展示 pod 类型保存对象
2. Pod 页可使用已保存 pod 对象直接巡检
3. Pod 页可编辑 pod 保存对象
4. Pod 页可保存新的 pod 对象
5. Pod 页可导入、导出、删除 pod 对象

## API 契约影响

本次未改 API 契约。

没有修改：

1. 后端接口
2. 后端 schema
3. 前端 `api/types.ts`
4. 契约文档

## 验证结果

已执行定向测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run src/pages/NamespaceInspectionPage.test.tsx
npm test -- --run src/pages/PodInspectionPage.test.tsx
```

结果：

- `NamespaceInspectionPage.test.tsx`：`5 tests passed`
- `PodInspectionPage.test.tsx`：`3 tests passed`

## 当前结论

第 18 节指出的保存对象类型分流问题已经处理到方案 A：

1. namespace 保存对象只在名称空间页展示和使用
2. pod 保存对象只在 Pod 页展示和使用
3. 名称空间页不会再把 pod 保存对象误当 namespace 对象执行

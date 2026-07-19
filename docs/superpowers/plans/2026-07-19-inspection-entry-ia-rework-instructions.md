# 巡检入口信息架构重构指令

## 背景

用户对当前页面的反馈很明确：

1. 页面内容全部平铺，导致一个页面非常长。
2. 不常用的保存、导入、导出、编辑对象等内容占据主页面。
3. 主流程没有下拉选择，用户要么手填，要么看到大量无关内容。
4. 名称空间巡检、Pod 巡检、日志/describe 巡检的边界不清楚。
5. 导入内容、导出内容必须用弹窗，不允许平铺 textarea。

这不是样式问题，是信息架构问题。不要继续只调 CSS。

## 产品目标

把巡检入口重构成“选择范围 -> 执行巡检 -> 查看结果”的工作流。

主页面只放高频操作：

1. 选择名称空间。
2. 选择巡检模式。
3. 选择可选过滤条件。
4. 点击巡检。
5. 查看本次结果摘要和证据入口。

低频操作必须收起：

1. 保存常用范围。
2. 导入。
3. 导出。
4. 编辑保存对象。
5. 删除保存对象。

## 必须先做的产品定义

### 1. 名称空间巡检

用户通过下拉框选择名称空间，不再优先手填。

行为：

1. 页面加载后自动调用现有名称空间发现接口。
2. 名称空间选择使用下拉框，支持搜索。
3. 用户选择名称空间后，点击“巡检名称空间”。
4. 系统检查该名称空间下 Pod 状态、容器状态、事件、日志关键字、关联对象。
5. 结果摘要展示异常 Pod 数、正常/已完成 Pod 数、异常分类。
6. 证据详情放抽屉或详情区域，不要全部铺在主页面。

允许保留手动输入入口，但只能作为“高级输入”或“找不到名称空间时手动输入”，不能是主入口。

### 2. Pod 巡检

Pod 巡检不是一上来让用户手填 Pod 名称。

用户路径：

1. 先选择名称空间。
2. 再选择巡检范围：
   - `全部 Pod`
   - `Label Selector`
   - `单个 Pod`
3. `全部 Pod`：巡检该名称空间所有 Pod 的状态、日志关键字、describe 摘要。
4. `Label Selector`：输入或选择 Label Selector 后，巡检匹配范围内的 Pod。
5. `单个 Pod`：从 Pod 下拉框选择单个 Pod 后巡检。

实现约束：

1. 如果现有后端没有 Pod 列表接口，前端可以先通过一次名称空间巡检结果生成 Pod 下拉框。
2. 不要为了做 Pod 下拉框立刻扩后端，除非现有接口完全无法支撑。
3. 如果 Label Selector 匹配多个 Pod，当前阶段按范围巡检展示多个 Pod，不要假装它是单 Pod。
4. 单 Pod 精确巡检才使用 `/inspections/pod/run`。
5. Label Selector 范围巡检优先使用 `/inspections/namespace/run` 的 `label_selector`。

### 3. 导入 / 导出

导入导出不能再平铺在页面。

必须改成弹窗：

1. “导入”按钮打开弹窗。
2. 弹窗中放导入 textarea、确认导入、取消。
3. “导出”按钮打开弹窗。
4. 弹窗中显示导出 JSON、复制按钮、关闭。
5. 主页面不出现“导入内容”“导出内容”的大 textarea。

### 4. 保存常用范围

保存功能是低频操作，不应该占主页面核心区域。

建议：

1. 主页面放一个“保存当前范围”次级按钮。
2. 点击后打开弹窗。
3. 弹窗里填写保存名称。
4. 已保存范围放在下拉框或“常用范围”折叠面板。
5. 编辑/删除保存对象只能在弹窗或折叠面板里，不要铺满页面。

## 任务拆分

### 任务一：让 “统一契约与数据模型” agent 复核能力边界

目标：

确认现有 API 是否支撑下拉式巡检入口。

检查范围：

1. `frontend/src/api/client.ts`
2. `frontend/src/api/types.ts`
3. `backend/app/api/routes/discovery.py`
4. `backend/app/api/routes/inspections.py`
5. `backend/app/schemas/inspection.py`

需要回答：

1. 当前是否已有名称空间发现接口可用于下拉框。
2. 当前是否已有 Pod 列表能力。
3. 如果没有 Pod 列表，是否可以用名称空间巡检结果临时生成 Pod 下拉框。
4. Label Selector 范围巡检是否可以复用 namespace inspection。
5. 是否需要新增最小 API。如果需要，写清楚原因和字段，不要直接扩。

边界：

1. 只复核，不改 UI。
2. 不新增字段，除非确认现有接口无法实现核心路径。
3. 不改健康判定。

输出：

```text
worklog/codex-inspection-entry-ia-contract-review-2026-07-19.md
```

### 任务二：让 “前端工作台与人性化 UI” agent 重构入口

目标：

重构 `NamespaceInspectionPage` 和 `PodInspectionPage` 的信息架构，消除平铺长页面。

重点文件：

1. `frontend/src/pages/NamespaceInspectionPage.tsx`
2. `frontend/src/pages/PodInspectionPage.tsx`
3. `frontend/src/pages/NamespaceInspectionPage.test.tsx`
4. `frontend/src/pages/PodInspectionPage.test.tsx`
5. `frontend/src/styles.css`

必须实现：

1. 名称空间选择改为下拉框为主。
2. 名称空间巡检页面不再默认展示导入/导出 textarea。
3. Pod 巡检页面支持先选名称空间，再选范围模式：
   - `全部 Pod`
   - `Label Selector`
   - `单个 Pod`
4. Label Selector 巡检展示多 Pod 结果，不要误称单 Pod。
5. 单个 Pod 巡检使用 Pod 下拉框，不再要求用户优先手填。
6. 保存当前范围、导入、导出改为弹窗。
7. 主页面首屏必须能看清楚：
   - 当前选择范围
   - 主巡检按钮
   - 最近一次巡检摘要
8. 详情内容使用抽屉、折叠、左右布局，不要所有证据纵向平铺。

推荐页面结构：

```text
巡检入口
  顶部：巡检类型切换 / 当前模式说明
  主卡片：名称空间下拉 + 范围模式 + 过滤条件 + 巡检按钮
  次级按钮：保存当前范围 / 常用范围 / 导入 / 导出
  结果摘要：状态、异常数量、异常分类
  证据入口：查看 Pod 证据 / 查看关联对象 / 模板匹配
```

UI 要求：

1. 不要大面积 textarea 常驻。
2. 不要一屏出现多个同等强调的大按钮。
3. 主按钮只能 1 到 2 个。
4. 次级操作用文字按钮、弹窗、折叠区。
5. 文案要符合运维使用习惯，不要写“保存名称”这种让人不知道填什么的标签；改成“常用范围名称”。

测试要求：

1. 名称空间下拉能展示发现到的 namespace。
2. 选择 namespace 后能运行名称空间巡检。
3. 导入/导出 textarea 默认不出现在页面，点击按钮后才在弹窗出现。
4. Pod 巡检选择 `全部 Pod` 时，不要求填写 pod 名称。
5. Pod 巡检选择 `Label Selector` 时，按 label selector 调用 namespace inspection。
6. Pod 巡检选择 `单个 Pod` 时，才调用 pod inspection。
7. 保存当前范围通过弹窗完成。
8. 白名单忽略入口不能丢。

验收命令：

```bash
cd frontend && npm test -- --run src/pages/NamespaceInspectionPage.test.tsx src/pages/PodInspectionPage.test.tsx src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

输出：

```text
worklog/codex-inspection-entry-ia-frontend-2026-07-19.md
```

### 任务三：让 “K8s 采集与证据抽取” agent 暂不开发

当前反馈主要是前端入口问题，不要让后端 agent 先扩接口。

只有在 “统一契约与数据模型” 明确确认现有接口无法支撑 Pod 下拉或 Label Selector 路径时，才允许后端做最小 API。

如果需要后端 API，必须另开小切片，不能和前端大改混在一起。

## 验收标准

本轮通过标准：

1. 页面不再因为导入/导出 textarea 变长。
2. 名称空间巡检主流程是下拉选择 namespace 后巡检。
3. Pod 巡检主流程是选择 namespace 后选择范围模式。
4. Label Selector 是范围巡检，不伪装成单 Pod。
5. 单 Pod 巡检有 Pod 下拉选择。
6. 主页面首屏能看清主操作，不再所有功能平铺。
7. 原有白名单忽略、模板匹配、证据查看不丢。
8. 前端测试和 build 通过。

## 禁止事项

1. 不要继续在现有长页面上加新卡片。
2. 不要把导入/导出 textarea 留在主页面。
3. 不要让用户必须手填 namespace 才能巡检。
4. 不要把 Label Selector 多 Pod 范围巡检说成单 Pod。
5. 不要先扩后端 API 再想 UI。
6. 不要改 Pod 健康判定。
7. 不要改故障模板 matcher。

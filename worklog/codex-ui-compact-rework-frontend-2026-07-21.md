# 2026-07-21 UI 紧凑化返工前端工作记录

## 本轮范围

只处理前端工作台与人性化 UI 相关内容，未改后端、模板页、关键字库页业务逻辑。

涉及文件：

1. `frontend/src/pages/PodInspectionPage.tsx`
2. `frontend/src/pages/NamespaceInspectionPage.tsx`
3. `frontend/src/pages/AutoInspectionPage.tsx`
4. `frontend/src/styles.css`
5. `frontend/src/pages/PodInspectionPage.test.tsx`
6. `frontend/src/pages/NamespaceInspectionPage.test.tsx`

## 完成内容

### 1. 日志巡检页合并

将原 `PodInspectionPage` 提升为统一的 `日志巡检` 工作台，覆盖三种范围：

1. `全部 Pod`
2. `Label Selector`
3. `单个 Pod`

`NamespaceInspectionPage` 不再维护一套独立长页面，而是直接复用合并后的日志巡检页，默认进入 `全部 Pod` 模式。这样保留旧路由兼容，但导航职责回到单页。

### 2. Label Selector 自动发现接入

日志巡检页已接入 `useDiscoverNamespaceLabels(namespace)`：

1. 先下拉选择自动发现候选项
2. 保留“手动输入”作为高级入口
3. 不把自动发现候选保存成系统配置

### 3. 页面紧凑化

处理重点：

1. 常用范围从大卡片改成紧凑表格
2. Pod 列表、名称空间列表、批量结果组加固定高度滚动容器
3. `describe`、事件、日志命中、导入导出 JSON 统一进入可滚动代码框
4. 次级操作按钮改成更小的 `mini-button`
5. 弹窗统一套用 `modal-card-polished`

### 4. “一直下拉像跳到自动巡检页”的处理

本轮没有发现路由自动跳转问题，前端现状更像是：

1. 日志巡检页内容过长
2. Pod 列表、结果详情、常用范围都纵向平铺
3. 用户持续滚动时会产生“已经换页”的错觉

本次通过固定高度滚动容器和左右分栏减少整页纵向增长，属于 UI 侧根因修正，不是额外加路由 hack。

## 测试与验证

已执行：

1. `cd frontend && npm test -- --run`
2. `cd frontend && npm run build`

结果：

1. 前端测试通过
2. 前端构建通过

## 追加记录：第二阶段模板检查与故障模板 UI

### 1. 模板检查结果改成“先结论，后证据”

涉及文件：

1. `frontend/src/features/diagnosis/DiagnosisResultPanel.tsx`
2. `frontend/src/pages/DiagnosisPage.test.tsx`
3. `frontend/src/pages/AutoInspectionPage.test.tsx`
4. `frontend/src/styles.css`

完成点：

1. 命中模板继续优先展示，但增加了顶部紧凑摘要表格，第一眼先看到：
   - 模板名
   - 结论
   - 命中条件数
   - 建议动作
2. 每个模板卡片改成 `details` 展开模式：
   - 默认命中模板展开
   - 未命中模板仍保持折叠
   - 采集失败模板放在“无法判断”区域
3. 关键证据不再直接平铺成长文本，而是改成：
   - 证据摘要
   - 单条证据 JSON 代码框
4. 证据区统一使用可滚动代码框，长内容不再撑高页面。

### 2. 故障模板页改成“列表主视图 + 步骤化录入弹窗”

涉及文件：

1. `frontend/src/pages/TemplatesPage.tsx`
2. `frontend/src/pages/TemplatesPage.test.tsx`
3. `frontend/src/styles.css`

完成点：

1. 主页面不再常驻长表单。
2. 首页首屏只保留：
   - 模板总数
   - 当前模式摘要
   - 新增模板入口
   - 导入 / 导出入口
   - 紧凑模板列表
3. 新增 / 编辑模板统一进入 `模板录入器` 弹窗：
   - 仍保留原 5 步流程
   - 不改保存 payload
   - 编辑旧模板仍可回填
4. 模板列表改成紧凑表格：
   - 模板
   - 状态
   - 摘要
   - 对象组 / 条件数
   - 操作
5. 详情改成行内折叠区，不再用大卡片整页堆叠。
6. 导入 / 导出弹窗里的 JSON 输入输出都统一改为可滚动代码框。

### 3. 第二阶段本轮验证

已执行：

1. `cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx`
2. `cd frontend && npm test -- --run`
3. `cd frontend && npm run build`

结果：

1. `DiagnosisPage`、`TemplatesPage` 定向测试通过
2. 前端全量测试通过
3. 前端构建通过

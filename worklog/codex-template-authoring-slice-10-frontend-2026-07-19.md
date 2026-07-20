# 2026-07-19 故障模板录入页体验重构（切片 10）工作记录

## 范围

按照 [2026-07-19-template-authoring-ux-slice-10-instructions.md](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md) 只处理前端模板录入页体验重构。

本轮未修改：

1. 后端模板契约。
2. matcher。
3. diagnosis response。
4. 自动巡检页、名称空间巡检页、Pod 巡检页。

## 已完成内容

### 1. 模板录入改为步骤流

文件：

1. [TemplatesPage.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/pages/TemplatesPage.tsx)

完成点：

1. 模板录入拆成 5 步：
   - 基本信息
   - 目标范围
   - 匹配条件
   - 原因与建议
   - 预览与保存
2. 首屏突出当前步骤、下一步动作和模板总数，不再把所有字段一次性铺满。
3. 保存前提供显式缺项提示，不再只依赖按钮禁用。
4. 预览步骤展示模板摘要、对象组摘要、条件摘要和原因建议摘要。

### 2. 条件录入改为运维文案

完成点：

1. 条件类型显示为中文业务文案：
   - 日志包含关键字
   - Pod 状态匹配
   - 重启次数达到阈值
   - 事件包含关键字
   - 关联对象状态异常
2. 运算符显示为中文业务文案：
   - 包含
   - 等于
   - 属于任一值
   - 大于等于
   - 小于等于
3. 提交时仍保持后端枚举值，不改变 payload 契约。
4. 条件步骤顶部补充 AND / OR 语义说明。

### 3. 对象组与条件改为卡片摘要

完成点：

1. 对象组和条件块都改成可展开卡片。
2. 支持新增、删除、展开编辑。
3. 条件绑定对象组时仍跟随后端 `target_ref` 语义。
4. 编辑已有模板时可按步骤回填。

### 4. 导入导出改成弹窗

完成点：

1. 默认页面不展示导入 JSON textarea。
2. 点击“导入模板”后才打开导入弹窗。
3. 点击“导出模板”后才打开导出弹窗并展示 JSON。
4. 关闭弹窗不会影响当前步骤表单状态。

### 5. 模板列表摘要化

完成点：

1. 模板列表默认展示名称、启用状态、原因、对象组数、条件数、条件关系。
2. 详情下沉到折叠区。
3. 列表操作保留：
   - 编辑
   - 启用 / 停用
   - 删除

### 6. 样式补充

文件：

1. [styles.css](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/styles.css)

完成点：

1. 新增步骤芯片样式。
2. 新增对象组 / 条件折叠卡片样式。
3. 新增提示卡片和缺项警示样式。

### 7. 测试更新

文件：

1. [TemplatesPage.test.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/pages/TemplatesPage.test.tsx)

覆盖点：

1. 默认只看到当前步骤，不看到导入导出 textarea。
2. 可进入目标范围步骤并修改对象组信息。
3. 条件步骤显示中文文案，但提交 payload 保持后端枚举值。
4. 预览步骤可看到显式缺项提示。
5. 导入 / 导出通过弹窗触发。
6. 编辑已有模板可回填步骤表单。

## 验收记录

已通过：

1. `cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx`
2. `cd frontend && npm test -- --run`
3. `cd frontend && npm run build`
4. `git status --short`

## Review 后补充修复

后续 review 发现一个兼容性问题：

1. 当旧模板或兼容导入模板只有 `target_groups`、没有 `targets` 时，编辑回填会退回默认对象组。
2. 这会导致名称空间、Label Selector、Pod 名称模式和资源范围在编辑时丢失。

已补充最小修复：

1. `toTargetDrafts()` 在 `targets` 为空时优先读取 `target_groups`。
2. `target_groups[].object_scope` 会转换成 `resource_scope`。
3. 补充测试覆盖 `targets: [] + target_groups.object_scope` 的旧模板编辑回填。

Review 后重新验证：

1. `cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx`
   - 通过，11 tests passed。
2. `cd frontend && npm test -- --run`
   - 通过，53 tests passed。
3. `cd frontend && npm run build`
   - 通过。

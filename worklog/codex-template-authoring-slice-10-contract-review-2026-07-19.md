# Worklog: 模板录入页切片 10 契约复核

## 时间

- 日期：2026-07-19
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md` 第一步，只做模板录入页相关的轻量契约复核，确认本切片是否可以完全前端实现，不主动改后端契约。

## 检查范围

已检查：

1. `frontend/src/api/types.ts`
2. `backend/app/schemas/template.py`
3. `frontend/src/pages/TemplatesPage.tsx`
4. `frontend/src/pages/TemplatesPage.test.tsx`
5. `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`
6. `docs/superpowers/plans/2026-07-19-diagnosis-template-result-slice-9-acceptance-and-next.md`

## 复核结论

### 1. `FaultTemplate` 前后端契约仍一致

前端 `FaultTemplate` 当前包含：

1. `id`
2. `name`
3. `scenario`
4. `targets`
5. 兼容输出 `target_groups`
6. `match_conditions`
7. `joint_rule`
8. `reason`
9. `suggestion`
10. `command`
11. `risk_note`
12. `enabled`

后端 `backend/app/schemas/template.py` 的 `FaultTemplateRead` / `FaultTemplateBase` 也仍围绕同一组字段工作。

结论：

- 当前模板录入页 UI 重构不需要新增模板字段
- 保存 payload 仍可继续使用既有 `targets + match_conditions + joint_rule` 主结构

### 2. `TemplateTarget` 主用字段与兼容字段边界清楚

当前主用字段：

1. `target_ref`
2. `namespace`
3. `label_selector`
4. `pod_name_pattern`
5. `resource_scope`

兼容输出字段：

1. `target_groups`
2. `ref`
3. `name`
4. `object_scope`

关键结论：

- 前端新 UI 应主用 `targets`
- 编辑旧模板时可以继续读取 `target_groups` 兼容输出
- 但 UI 重构不能再把 `target_groups/object_scope` 当作主写入结构

### 3. `object_scope` 与 `resource_scope` 语义未变化

后端仍按以下语义工作：

1. 新结构主用 `resource_scope`
2. 旧结构 `object_scope` 只用于兼容输入/兼容输出
3. `target_groups[].object_scope` 会在归一化时转换成 `targets[].resource_scope`

结论：

- 前端这轮只需要把“资源范围”UI 绑定到 `resource_scope`
- 不需要新增字段，也不应该反向强化 `object_scope`

### 4. `TemplateCondition` 与运算符契约仍一致

前端类型与后端 schema 当前一致：

条件类型：

1. `pod_status`
2. `log_keyword`
3. `event_keyword`
4. `restart_count`
5. `related_object_status`

运算符：

1. `equals`
2. `in`
3. `contains`
4. `gte`
5. `lte`

结论：

- 本切片可以只做“中文业务文案映射”
- 不需要新增条件类型
- 不需要新增运算符
- 不需要改 matcher

### 5. 本切片可以完全前端实现

结论：可以。

原因：

1. 当前模板录入页已经能创建、编辑、启停、删除模板
2. 现有 API payload 已能表达：
   - 基本信息
   - 多对象组
   - 多条件
   - AND/OR
   - 原因与建议
3. 导入/导出能力已存在，只是当前 UI 组织不合理
4. 本轮目标是信息架构与交互重构，不是表达能力不足

因此：

- 本切片应优先纯前端完成
- 不建议为了步骤化 UI 先改后端

## 对前端重构的具体契约边界

前端可以放心重构以下内容，而不改后端：

1. 录入步骤拆分
2. 中文文案映射
3. 对象组卡片化
4. 条件卡片化
5. 预览步骤
6. 导入/导出弹窗化
7. 编辑回填流程

但必须遵守：

1. 保存时主写 `targets`
2. `match_conditions[].target_ref` 必须仍绑定有效对象组
3. `joint_rule.operator` 仍只用 `AND/OR`
4. 不要把 UI 内部草稿结构直接泄漏成新的 API 结构

## 不建议在本切片做的后端改动

当前未发现必须改契约的地方，因此本切片不建议：

1. 新增模板字段
2. 新增模板步骤状态字段
3. 新增模板 UI 专用 summary 字段
4. 删除兼容字段
5. 调整 matcher 或 diagnosis response

## 当前结论

模板录入页切片 10 可以完全前端实现。

当前最合理的做法：

1. 保持模板契约不变
2. 前端主用 `targets / match_conditions / joint_rule`
3. 兼容读取 `target_groups`
4. 通过步骤化和弹窗化重构页面体验

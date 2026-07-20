# 切片 10：故障模板录入页体验重构指令

## 背景

截至切片 9，故障模板匹配结果已经增强，后端 matcher、diagnosis response 和前端结果展示已完成基础可用闭环。下一步不要继续扩 matcher，而是解决“故障模板录入页过长、所有能力平铺、用户不知道下一步做什么”的问题。

当前 `frontend/src/pages/TemplatesPage.tsx` 仍把模板基础信息、对象组、条件块、原因建议、导入导出和模板列表放在同一主视图里。这个页面能完成操作，但不符合“降低运维工作量”的产品目标。

本切片目标是把故障录入变成更像运维人员填写“故障经验”的流程，而不是让用户面对一堆字段。

## 总目标

1. 故障模板录入必须按步骤组织，用户只在当前步骤看到必要字段。
2. 导入/导出保留，但必须放到弹窗、抽屉或更多操作中，不能常驻占用主页面。
3. 条件录入要使用运维语言，减少 `log_keyword`、`pod_status`、`operator` 这类裸技术枚举对用户的暴露。
4. 多对象组、多条件、AND/OR 的关系必须更清楚。
5. 本切片不改变后端匹配语义，不改变 diagnosis response，不改变名称空间巡检入口。

## 必须参考的文档和代码

所有参与 agent 必须先阅读：

1. `docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`
2. `docs/superpowers/plans/2026-07-19-diagnosis-template-result-slice-9-acceptance-and-next.md`
3. `frontend/src/pages/TemplatesPage.tsx`
4. `frontend/src/pages/TemplatesPage.test.tsx`
5. `frontend/src/api/types.ts`
6. `backend/app/schemas/template.py`

## 分工与顺序

本切片不能所有 agent 同时开工。正确顺序是：

1. “统一契约与数据模型” 先做契约复核。
2. 如果契约复核结论是不需要改后端契约，再让 “前端工作台与人性化 UI” 开始实现。
3. “前端工作台与人性化 UI” 完成并写 worklog 后，再让 “故障模板与匹配引擎” 做只读复核。

原因：

1. 前端 UI 会大量消费模板字段，必须先确认字段边界。
2. matcher 不应和 UI 重构并行修改，否则难以判断问题来自录入 payload 还是匹配逻辑。
3. 本切片主要解决体验问题，不应扩散成后端重构。

### 第一步：让 “统一契约与数据模型” 做轻量契约复核

只做复核，不主动改业务实现。

任务：

1. 核对前端 `FaultTemplate`、`TemplateTarget`、`TemplateCondition`、`TemplateConditionOperator` 与后端 `backend/app/schemas/template.py` 是否仍一致。
2. 特别核对 `targets`、兼容输出 `target_groups`、`object_scope`、`resource_scope` 的语义，避免前端 UI 重构时误用旧兼容字段。
3. 确认本切片是否可以完全前端实现。
4. 如果发现必须改契约，先写清楚原因和最小改动建议，不要直接扩大范围。

边界：

1. 不改 matcher。
2. 不改 diagnosis response。
3. 不新增模板字段，除非确认现有字段无法表达当前 UI。
4. 不删除兼容字段。

输出：

`worklog/codex-template-authoring-slice-10-contract-review-2026-07-19.md`

### 第二步：让 “前端工作台与人性化 UI” 重构模板录入页

必须等待“统一契约与数据模型”的复核结论。如果结论是不需要改契约，则只改前端。

任务：

1. 将 `TemplatesPage` 主录入区域重构为分步骤或分区折叠流程：
   - 基本信息：模板名称、场景标识、启用状态。
   - 目标范围：对象组、名称空间、Label Selector、Pod 名称模式、资源范围。
   - 匹配条件：绑定对象组、条件类型、匹配方式、期望值、启用状态、AND/OR 关系。
   - 原因与建议：诊断原因、处理建议、建议命令、风险说明。
   - 预览与保存：展示最终模板摘要，再提交保存。
2. 首页首屏只展示当前步骤、下一步动作、已有模板列表摘要，不能把全部字段一次性铺满。
3. 条件类型要显示成运维可理解的文案：
   - 日志包含关键字。
   - Pod 状态匹配。
   - 重启次数达到阈值。
   - 事件包含关键字。
   - 关联对象状态异常。
4. 运算符也要显示业务文案，保留实际 value 不变：
   - `contains` 显示为“包含”。
   - `equals` 显示为“等于”。
   - `in` 显示为“属于任一值”。
   - `gte` 显示为“大于等于”。
5. 对象组和条件必须用卡片或列表摘要展示，支持展开编辑、添加、删除，避免长表单连续堆叠。
6. AND/OR 关系要在条件步骤顶部明确解释：
   - AND：所有启用条件都满足才命中故障。
   - OR：任一启用条件满足就命中故障。
7. 导入/导出模板 JSON 改为次级入口，使用弹窗或抽屉：
   - 默认不展示 JSON textarea。
   - 点击“导入模板”才出现导入 textarea。
   - 点击“导出模板”才出现导出结果。
   - 弹窗/抽屉可关闭，关闭后不影响主录入状态。
8. 模板列表保留，但列表只展示摘要和主要操作；详情可以折叠、抽屉或卡片展开。
9. 保存校验必须在 UI 上明确指出缺少哪个步骤的必要信息，不要只让按钮不可点。
10. 保持原有 API payload 结构，不为了 UI 重构改变后端契约。

边界：

1. 不改 `backend/app/services/diagnosis.py`。
2. 不改模板匹配算法。
3. 不改自动巡检页、名称空间巡检页、Pod 巡检页。
4. 不新增 AI 解释。
5. 不把导入/导出放回主页面常驻区域。
6. 不删除模板导入/导出能力，因为它属于配置迁移能力。

建议测试：

1. `TemplatesPage.test.tsx` 覆盖默认只看到第一步或当前步骤，不看到导入 JSON textarea。
2. 覆盖点击下一步进入目标范围。
3. 覆盖新增对象组、修改名称空间和 Label Selector。
4. 覆盖新增条件，并验证条件类型/运算符显示为中文文案但提交 payload 仍使用后端枚举值。
5. 覆盖预览步骤能看到对象组、条件、原因、建议摘要。
6. 覆盖保存模板请求体保持 `targets` 和 `match_conditions` 结构不变。
7. 覆盖导入/导出入口通过弹窗或抽屉打开，默认不占据页面。
8. 覆盖编辑已有模板时能正确回填步骤表单。

输出：

`worklog/codex-template-authoring-slice-10-frontend-2026-07-19.md`

### 第三步：让 “故障模板与匹配引擎” 做只读复核

只有当前端完成后再做。原则上不改代码，除非发现 UI 生成的 payload 会破坏匹配语义。

任务：

1. 复核前端保存出来的 `targets` 和 `match_conditions` 能被现有 matcher 正确消费。
2. 复核多 Pod 命中同一对象组时，仍是任一 Pod 满足即可。
3. 复核白名单日志命中不会被模板日志条件误判为有效证据。
4. 复核 AND/OR 在 UI 文案和 matcher 语义上保持一致。

边界：

1. 不新增 matcher 功能。
2. 不改 diagnosis response。
3. 不扩大采集字段。

输出：

`worklog/codex-template-authoring-slice-10-matcher-review-2026-07-19.md`

## 可直接派发的指令

### 发给 “统一契约与数据模型”

```text
让 “统一契约与数据模型” 参考 docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md，先做切片 10 的契约复核。

只读复核为主，不主动改业务实现。重点核对 frontend/src/api/types.ts 与 backend/app/schemas/template.py 里 FaultTemplate、TemplateTarget、TemplateCondition、TemplateConditionOperator、targets、target_groups、object_scope、resource_scope 是否一致，确认故障模板录入页重构能否完全前端完成。

不要改 matcher，不要改 diagnosis response，不要新增模板字段，除非明确证明现有字段无法表达。完成后写 worklog/codex-template-authoring-slice-10-contract-review-2026-07-19.md，并明确结论：前端是否可以开始实现。
```

### 发给 “前端工作台与人性化 UI”

```text
让 “前端工作台与人性化 UI” 参考 docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md，以及 “统一契约与数据模型” 留下的 worklog，重构故障模板录入页。

目标是把 frontend/src/pages/TemplatesPage.tsx 从长表单改成更人性化的分步骤/折叠式录入流程：基本信息、目标范围、匹配条件、原因与建议、预览与保存。导入/导出必须放弹窗、抽屉或更多操作里，默认不能展示 JSON textarea。条件类型和运算符要展示中文业务文案，但提交 payload 必须继续使用后端枚举值。

不要改后端 matcher，不要改 diagnosis response，不要改自动巡检页、名称空间巡检页、Pod 巡检页。补充或更新 frontend/src/pages/TemplatesPage.test.tsx，至少覆盖步骤切换、默认不展示导入 textarea、新增对象组、新增条件、保存 payload、导入/导出弹窗、编辑回填。

完成后执行：
cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build

完成后写 worklog/codex-template-authoring-slice-10-frontend-2026-07-19.md。
```

### 发给 “故障模板与匹配引擎”

```text
让 “故障模板与匹配引擎” 参考 docs/superpowers/plans/2026-07-19-template-authoring-ux-slice-10-instructions.md，以及 “前端工作台与人性化 UI” 留下的 worklog，做切片 10 的匹配语义复核。

原则上只读复核，不改代码。重点确认前端保存的 targets 和 match_conditions 能被现有 matcher 正确消费；多 Pod 匹配同一对象组时仍是任一 Pod 满足即可；白名单日志命中不会作为有效故障证据；AND/OR 文案与 matcher 语义一致。

不要新增 matcher 功能，不要改 diagnosis response，不要扩大采集字段。如果发现 UI 生成 payload 破坏匹配语义，先写清楚具体字段、影响路径和最小修复建议。完成后写 worklog/codex-template-authoring-slice-10-matcher-review-2026-07-19.md。
```

## 验收标准

必须满足：

1. 模板录入页不再是一整页平铺长表单。
2. 用户可以按步骤完成模板录入。
3. 导入/导出不在主页面常驻展示。
4. 条件类型和运算符有中文业务文案。
5. 保存 payload 与现有后端契约一致。
6. 编辑旧模板不会丢失对象组、条件、原因、建议、启用状态。
7. 模板列表仍可启停、编辑、删除。
8. 没有修改 matcher、diagnosis response、巡检入口。

## 验收命令

前端必须执行：

```bash
cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

如果“统一契约与数据模型”或“故障模板与匹配引擎”实际改了后端代码，还必须执行：

```bash
python3 -m pytest -q backend/tests
```

最终提交前必须执行：

```bash
git status --short
```

## 交付给用户前的人工检查

构建镜像前，人工打开页面检查：

1. 进入故障模板页后，首屏是否清楚告诉用户当前在录入哪一步。
2. 是否能不用滚很长页面就完成主要路径。
3. 是否能看懂“目标范围”和“匹配条件”的关系。
4. 导入/导出是否只在点击后出现。
5. 编辑已有模板是否比从零录入更省力。

## 暂不进入的后续事项

这些不属于切片 10：

1. 模板命中后的最终故障报告页。
2. 模板版本管理。
3. 模板批量启停。
4. 模板按集群环境隔离。
5. 自动根据巡检结果生成模板。
6. AI 总结或自动推理。

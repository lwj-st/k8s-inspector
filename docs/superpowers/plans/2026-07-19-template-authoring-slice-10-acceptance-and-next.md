# 切片 10 验收记录与后续开发指令

## 验收结论

切片 10 已完成，结论：可以进入下一切片。

本轮完成的是“故障模板录入页体验重构”，核心目标是把故障模板录入从长表单改为可分步完成的运维经验录入流程。

## 已确认完成

1. `TemplatesPage` 已拆成 5 步：
   - 基本信息
   - 目标范围
   - 匹配条件
   - 原因与建议
   - 预览与保存
2. 首屏不再展示所有字段，降低页面长度和认知负担。
3. 导入/导出已从主页面移入弹窗。
4. 条件类型和运算符已使用中文业务文案展示，提交 payload 仍保持后端枚举。
5. 对象组和条件已卡片化，支持新增、删除、展开编辑。
6. 预览步骤能展示模板、对象组、条件、原因和建议摘要。
7. 保存前有显式缺项提示，不再只依赖按钮禁用。
8. 模板列表改为摘要展示，详情下沉到折叠区。
9. 兼容旧模板编辑：当 `targets` 为空但存在 `target_groups` 时，不会丢失名称空间、Label Selector、Pod 名称模式和资源范围。

## Review 修复点

Review 发现并已修复：

1. `frontend/src/pages/TemplatesPage.tsx` 中 `toTargetDrafts()` 原先在 `template.targets.length === 0` 时直接返回默认对象组。
2. 这会导致旧模板或兼容导入模板编辑时丢失 `target_groups` 范围信息。
3. 已改为优先读取 `template.target_groups`，并将 `object_scope` 转换为 `resource_scope`。
4. 已在 `frontend/src/pages/TemplatesPage.test.tsx` 增加兼容旧模板编辑回填测试。

## 已执行验证

已通过：

```bash
cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx
```

结果：

1. 2 test files passed。
2. 11 tests passed。

已通过：

```bash
cd frontend && npm test -- --run
```

结果：

1. 8 test files passed。
2. 53 tests passed。

已通过：

```bash
cd frontend && npm run build
```

结果：

1. TypeScript build passed。
2. Vite production build passed。

## 当前风险

当前没有发现阻塞提交的问题。

仍建议构建镜像后人工看一遍页面：

1. 故障模板页首屏是否比之前短。
2. 新增模板是否能顺着步骤走完。
3. 导入/导出弹窗是否符合预期。
4. 编辑已有模板是否能正确回填。

## 切片 11 建议：关键字库与白名单管理页体验收口

### 为什么下一步做这个

现在名称空间巡检、Pod 巡检、模板录入和模板匹配主流程已经做过体验重构。剩下容易继续影响用户体验的是配置管理类页面：

1. 关键字库。
2. 白名单。

这两个页面直接影响日志异常判断和“手动忽略此报错”的使用体验。如果它们仍像配置表单，用户会不知道哪些规则正在影响巡检结果。

### 切片 11 目标

1. 关键字库页面要让用户清楚知道：
   - 当前有哪些关键字。
   - 哪些启用、哪些停用。
   - 严重程度是什么。
   - 会匹配哪些日志。
   - 导入/导出只作为迁移能力，不能常驻占页面。
2. 白名单页面要让用户清楚知道：
   - 哪些报错被忽略了。
   - 忽略作用在哪个 namespace、pod、container 或 label。
   - 忽略的是哪个关键字或哪类日志。
   - 该白名单是否仍启用。
3. 从巡检结果点击“忽略此报错”后，白名单页面能看懂这条规则来源。
4. 不改变关键字匹配语义。
5. 不改变白名单过滤语义。

### 分工顺序

本切片可以分两条线串行执行，不建议完全并行。

第一步：让 “统一契约与数据模型” 做契约复核。

第二步：让 “关键字库与白名单” 做功能与语义复核。

第三步：让 “前端工作台与人性化 UI” 做页面体验收口。

第四步：让 “K8s 采集与证据抽取” 做只读复核，确认日志证据和白名单过滤链路未被 UI 改动破坏。

## 可直接派发的指令

### 发给 “统一契约与数据模型”

```text
让 “统一契约与数据模型” 参考 docs/superpowers/plans/2026-07-19-template-authoring-slice-10-acceptance-and-next.md，先做切片 11 的契约复核。

只读复核关键字库与白名单相关前后端契约，重点看 frontend/src/api/types.ts、backend/app/schemas/keyword.py、backend/app/schemas/whitelist.py，以及对应 API 使用处。确认当前字段是否足够支撑页面体验收口：启停、严重程度、namespace/pod/container/label 范围、关键字、备注、导入导出。

不要改日志匹配语义，不要改白名单过滤语义，不要新增字段，除非明确证明现有字段无法表达 UI。完成后写 worklog/codex-keyword-whitelist-slice-11-contract-review-2026-07-19.md，并明确前端是否可以开始。
```

### 发给 “关键字库与白名单”

```text
让 “关键字库与白名单” 参考 docs/superpowers/plans/2026-07-19-template-authoring-slice-10-acceptance-and-next.md，以及 “统一契约与数据模型” 的 worklog，复核关键字库和白名单现有功能语义。

重点确认：关键字启停和严重程度是否影响日志命中；白名单是否按 namespace、pod、container、label、关键字等范围正确过滤；从巡检结果“忽略此报错”生成的白名单是否能被管理页表达清楚。

原则上不改后端逻辑。如果发现现有功能缺陷，只做最小修复并补测试。不要改模板 matcher，不要改巡检编排入口。完成后写 worklog/codex-keyword-whitelist-slice-11-domain-review-2026-07-19.md。
```

### 发给 “前端工作台与人性化 UI”

```text
让 “前端工作台与人性化 UI” 参考 docs/superpowers/plans/2026-07-19-template-authoring-slice-10-acceptance-and-next.md，以及切片 11 前置 worklog，重构关键字库和白名单管理页体验。

目标是配置管理清晰化，不是新增后端能力。关键字库页面要突出启用状态、严重程度、匹配内容、编辑入口；白名单页面要突出忽略范围、忽略对象、来源说明、启用状态。导入/导出必须放弹窗、抽屉或更多操作，默认不展示 JSON textarea。列表要摘要化，编辑放弹窗、抽屉或局部展开，避免长页面平铺。

必须保留已有能力：新增、编辑、删除、启停、导入、导出。不要改日志匹配语义，不要改白名单过滤语义，不要改巡检页面主流程。完成后补充或更新对应前端测试，并写 worklog/codex-keyword-whitelist-slice-11-frontend-2026-07-19.md。
```

### 发给 “K8s 采集与证据抽取”

```text
让 “K8s 采集与证据抽取” 参考 docs/superpowers/plans/2026-07-19-template-authoring-slice-10-acceptance-and-next.md，以及切片 11 前端和领域 worklog，做只读复核。

重点确认关键字库和白名单页面改动没有破坏日志证据输出结构，没有影响 KeywordHit.whitelisted、severity、keyword、namespace、pod、container 等字段的消费路径。原则上不改代码，除非发现 UI 或契约变更导致证据链断裂。完成后写 worklog/codex-keyword-whitelist-slice-11-evidence-review-2026-07-19.md。
```

## 切片 11 验收命令建议

前端如果只改页面：

```bash
cd frontend && npm test -- --run src/pages/KeywordsPage.test.tsx src/pages/WhitelistsPage.test.tsx src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

如果改了后端关键字或白名单逻辑：

```bash
python3 -m pytest -q backend/tests
```

最终提交前：

```bash
git status --short
```


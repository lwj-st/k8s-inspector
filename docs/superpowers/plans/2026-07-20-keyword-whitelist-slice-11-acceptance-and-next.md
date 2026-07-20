# 切片 11 验收记录与后续开发指令

## 验收结论

切片 11 已完成，结论：可以进入下一切片。

本轮完成的是“关键字库与白名单管理页体验收口”，核心目标是把配置管理页从表单堆叠改成摘要清晰、低频操作下沉的规则中心。

## 已确认完成

1. 关键字库与白名单页面顶部已增加配置说明区。
2. 首屏能看到：
   - 启用关键字数量。
   - 内置关键字数量。
   - 启用白名单数量。
3. 关键字列表已摘要化展示：
   - 关键字内容。
   - 启用状态。
   - 严重程度。
   - 类别。
   - 用途说明。
   - 内置/自定义规则。
4. 白名单列表已摘要化展示：
   - 忽略关键字。
   - 生效范围。
   - 启用状态。
   - 来源说明。
5. 新增/编辑关键字已进入弹窗。
6. 新增/编辑白名单已进入弹窗。
7. 关键字导入/导出已进入弹窗。
8. 白名单导入/导出已进入弹窗。
9. 默认页面不再常驻展示 JSON textarea。
10. 保留了新增、编辑、删除、启停、导入、导出能力。
11. 未修改后端关键字匹配语义。
12. 未修改白名单过滤语义。
13. 未修改巡检主流程。

## 已执行验证

已通过：

```bash
cd frontend && npm test -- --run src/pages/WhitelistsPage.test.tsx src/pages/AutoInspectionPage.test.tsx
```

结果：

1. 2 test files passed。
2. 25 tests passed。

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

## Review 结论

当前没有发现阻塞提交的问题。

保留风险：

1. 状态徽标组件仍直接显示英文状态值，例如 `enabled`、`disabled`、`info`、`warning`。
2. 这不是切片 11 新增的问题，但在模板页、关键字页、白名单页会继续影响中文产品体验。
3. 建议下一切片集中处理状态文案和少量页面细节，不要混入后端功能开发。

## 切片 12 建议：全局状态文案与页面细节收口

### 为什么下一步做这个

当前主流程页面已经做过多轮体验重构，但仍有一些横向 UI 细节会让系统显得“不像产品”：

1. `StatusBadge` 直接显示英文状态。
2. 有些状态是技术值，不适合直接给运维用户看。
3. 模板、关键字、白名单等配置页更需要中文状态文案。
4. 如果不统一处理，后续每个页面都会各自硬编码，容易互相影响。

### 切片 12 目标

1. 统一 `StatusBadge` 的显示文案。
2. 保持原有状态颜色判断逻辑不被破坏。
3. 不改变 API response。
4. 不改变巡检健康判断。
5. 不改变模板匹配语义。
6. 补充测试，覆盖常见状态文案。

### 建议中文映射

基础状态：

1. `enabled` -> `启用`
2. `disabled` -> `停用`
3. `loading` -> `加载中`
4. `info` -> `信息`
5. `unknown` -> `未知`

健康状态：

1. `healthy` -> `健康`
2. `running` -> `运行中`
3. `ready` -> `就绪`
4. `succeeded` -> `已完成`
5. `completed` -> `已完成`
6. `warning` -> `告警`
7. `error` -> `异常`
8. `failed` -> `失败`
9. `degraded` -> `降级`

日志严重程度：

1. `critical` -> `严重`
2. `error` -> `高`
3. `warning` -> `中`
4. `info` -> `提示`

Pod 原生状态如 `CrashLoopBackOff`、`ImagePullBackOff`、`NotReady` 可以先保留原文，因为这些是 Kubernetes 常见诊断词。

### 分工顺序

本切片建议串行执行，不建议并行。

第一步：让 “前端工作台与人性化 UI” 实现 `StatusBadge` 文案映射与测试。

第二步：让 “统一契约与数据模型” 做只读复核，确认没有改 API 类型和 response。

第三步：让 “整体质量验收” 做全量验收。

## 可直接派发的指令

### 发给 “前端工作台与人性化 UI”

```text
让 “前端工作台与人性化 UI” 参考 docs/superpowers/plans/2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md，做切片 12：全局状态文案与页面细节收口。

目标是改 frontend/src/components/StatusBadge.tsx，让常见系统状态显示中文文案，但保持原有状态颜色判断逻辑。不要改 API response，不要改后端，不要改巡检健康判断，不要改模板 matcher。

必须覆盖 enabled、disabled、loading、info、unknown、healthy、running、succeeded、completed、warning、error、failed、degraded、critical 的显示文案。Kubernetes 原生状态如 CrashLoopBackOff、ImagePullBackOff、NotReady 可以先保留原文。

新增或更新 StatusBadge 相关测试。如果现有页面测试因为英文状态断言失败，要改成中文断言。完成后执行：
cd frontend && npm test -- --run
cd frontend && npm run build

完成后写 worklog/codex-status-copy-slice-12-frontend-2026-07-20.md。
```

### 发给 “统一契约与数据模型”

```text
让 “统一契约与数据模型” 参考 docs/superpowers/plans/2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md，以及 “前端工作台与人性化 UI” 的 worklog，做切片 12 契约复核。

只读复核：确认 StatusBadge 只是显示层映射，没有修改 frontend/src/api/types.ts，没有要求后端返回中文状态，没有改变健康状态枚举和严重级别枚举。不要主动改代码，除非发现前端为显示文案而污染 API 类型。

完成后写 worklog/codex-status-copy-slice-12-contract-review-2026-07-20.md。
```

### 发给 “整体质量验收”

```text
让 “整体质量验收” 参考 docs/superpowers/plans/2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md，以及切片 12 前端和契约 worklog，做全量验收。

重点确认：状态徽标显示中文，颜色语义不变；Kubernetes 原生异常状态没有被错误翻译；模板页、关键字页、白名单页、名称空间巡检页、Pod 巡检页、自动巡检页没有出现测试回归。

执行：
cd frontend && npm test -- --run
cd frontend && npm run build
git status --short

如果未改后端，不需要跑 backend tests。完成后写 worklog/codex-status-copy-slice-12-final-review-2026-07-20.md。
```

## 切片 12 验收标准

1. 页面上不再直接显示 `enabled`、`disabled`、`info` 这类英文技术状态。
2. 状态颜色不倒退。
3. Kubernetes 原生诊断状态仍可识别。
4. 全量前端测试通过。
5. 前端构建通过。
6. 未改后端契约。


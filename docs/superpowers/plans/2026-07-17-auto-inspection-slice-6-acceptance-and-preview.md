# 自动巡检切片 6 验收与预览说明

## 结论

切片 6 验收通过。

本轮已经把“故障模板手动匹配”接入自动巡检流程：用户完成名称空间批量巡检后，可以在批量摘要区点击“运行模板匹配”，系统会按故障模板自身绑定的名称空间、label selector、Pod 名称模式和条件执行匹配，不要求用户再次手填巡检范围。

## 已验收能力

1. 后端 `/api/v1/diagnoses/run` 支持空请求体直接运行已启用模板。
2. 每个模板按自身 `targets` / 兼容 `target_groups` 采集目标范围。
3. 模板 target 的 `namespace` 和 `label_selector` 会传给 provider。
4. 模板 target 的 `pod_name_pattern` / 兼容 `name` 会过滤参与匹配的 Pod。
5. 同一个目标范围内匹配多个 Pod 时，任意一个 Pod 命中即可让该条件命中。
6. 日志关键字命中如果已进入白名单，不再作为模板匹配有效证据。
7. 单个模板采集失败只影响该模板结果，不中断整次模板匹配。
8. 结果返回已命中模板、未命中模板、matched 条件、unmatched 条件和证据摘要。
9. 自动巡检页批量摘要区新增“运行模板匹配”按钮，结果在右侧抽屉展示，避免继续拉长主页面。
10. 独立“故障模板检查”页面也支持直接运行模板匹配，不再暴露 namespace/scope 手填输入。

## 验证记录

已执行并通过：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py backend/tests/test_whitelist_api.py
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run src/pages/DiagnosisPage.test.tsx src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

- 后端相关测试：23 passed
- 后端全量测试：76 passed
- 前端相关测试：33 passed
- 前端全量测试：45 passed
- 前端构建：通过

## 怎么先看效果

先不要启动切片 7。当前优先让用户看真实界面效果，再根据反馈决定 UI 和体验修整范围。

本地预览方式：

```bash
cd backend
uvicorn app.main:app --reload
```

另开终端：

```bash
cd frontend
npm run dev
```

建议查看路径：

1. 进入自动巡检页。
2. 等系统自动发现名称空间。
3. 选择一个名称空间后点击“巡检选中”，或直接点击“巡检全部”。
4. 批量巡检摘要出现后，点击“运行模板匹配”。
5. 检查右侧抽屉是否能清楚看到：
   - 已命中模板
   - 未命中模板
   - 命中条件
   - 未命中条件
   - 证据摘要
6. 再进入“故障模板检查”页，确认不需要手填 namespace/scope，点击后直接运行模板匹配。

如果要连开发集群预览，需要后端进程使用对应 kubeconfig，例如：

```bash
KUBECONFIG=/Users/liwenjian1.vendor/.kube/config_A100_dev uvicorn app.main:app --reload
```

具体 provider 环境变量以当前项目配置为准，不要在未确认配置前改代码。

## 当前不再继续拆的新功能

切片 6 只负责“手动触发模板匹配入口”闭环，不负责以下内容：

1. 不做定时巡检。
2. 不做通知推送。
3. 不做 AI 总结。
4. 不展示完整日志原文和完整 describe 原文。
5. 不重构模板录入页。
6. 不把模板匹配结果做成最终故障报告页。

## 下一步开发指示

### 先暂停

让用户先看切片 6 效果。没有用户反馈前，不要让任何开发方向继续大改 UI 或扩展后端能力。

### 如果用户确认入口方向正确

让 “前端工作台与人性化 UI” 参考本文件、`docs/superpowers/plans/2026-07-12-auto-inspection-product-realignment.md`、`docs/superpowers/plans/2026-07-17-auto-inspection-slice-5-acceptance-and-slice-6-instructions.md` 做切片 7。

切片 7 目标：把自动巡检页和模板匹配结果页做成可用工作台，而不是功能堆叠页面。

边界：

1. 只改前端展示和交互。
2. 不改后端 API 契约。
3. 不改 matcher 语义。
4. 不新增模板字段。
5. 不做导入导出主入口。

必须解决：

1. 主页面过长的问题。
2. 按钮过大、层级不清的问题。
3. 标题和文案不贴近运维用户的问题。
4. 批量巡检结果、证据抽屉、模板匹配抽屉之间的操作关系不清楚的问题。
5. “下一步该点哪里”的引导不足问题。

验收命令：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

### 如果用户认为模板匹配结果信息不够

让 “故障模板与匹配引擎” 参考本文件继续做结果解释增强。

边界：

1. 优先复用 `template_match_results`、`matches`、`evidence_summary`。
2. 不把完整 namespace inspection 结果塞进诊断响应。
3. 不改 `TemplateConditionOperator` 枚举。
4. 不引入 AI 总结。

可做内容：

1. 优化每个模板的 `summary`，让它说明“为什么命中/为什么未命中”。
2. 保留每个条件的证据，不丢失 `target_ref`。
3. 对采集失败模板输出明确失败原因。
4. 补充 matcher 和 diagnosis API 回归测试。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
python3 -m pytest -q backend/tests
```

### 如果用户要求真实集群效果验证

让 “K8s 采集与证据抽取” 参考本文件做真实 kubeconfig 验证，不要先扩功能。

边界：

1. 只验证 provider 是否能支撑自动名称空间巡检、证据抽屉和模板匹配。
2. 不改 UI。
3. 不改模板录入契约。
4. 发现真实集群字段缺口时，先记录问题和最小修复建议，再改代码。

验收重点：

1. 自动发现名称空间是否完整。
2. 批量巡检是否能在合理时间完成。
3. Pod 状态、事件、日志关键字、相关对象状态是否有证据。
4. 模板匹配是否按模板绑定 namespace/label selector 执行。
5. 已白名单日志是否不会再次触发模板命中。

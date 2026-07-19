# 自动巡检切片 8 验收与下一步

## 验收结论

切片 8 验收通过。

本切片只改前端工作台体验，没有改后端 API、Pod 健康语义、白名单逻辑、故障模板 matcher。

## 已确认能力

1. 自动巡检页主操作区拆成“主操作”和“范围操作”，减少按钮堆在一起的问题。
2. “巡检选中 / 巡检全部”被放到主操作区，“全选当前结果 / 取消当前结果”被放到范围操作区。
3. 批量巡检摘要增加“正常名称空间”指标。
4. 批量巡检摘要增加“下一步建议”，根据失败、告警、全部正常给不同引导。
5. 批量结果按状态分组展示：
   - `巡检失败`
   - `需要处理`
   - `巡检正常`
6. 名称空间证据抽屉按“结论 -> 证据 -> 后续操作”重排。
7. 白名单忽略入口保留。
8. 模板匹配入口保留在批量巡检摘要区。
9. `Succeeded / Completed` 的正常展示没有被破坏。

## 验证记录

已执行：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 前端相关测试：35 passed
2. 前端全量：47 passed
3. 前端构建：通过

说明：

1. 本切片只改前端，因此未跑后端全量。
2. 当前测试能覆盖主要入口未丢失，但新增 UI 文案和分组标题主要靠现有页面测试间接保护。后续如果继续改工作台，建议补更直接的 UI 断言。

## 当前建议

先构建镜像看真实页面，不要马上继续扩新功能。

重点请用户确认：

1. 自动巡检页是否比之前短、主操作是否更清楚。
2. “巡检选中 / 巡检全部”和“全选 / 取消”是否符合使用习惯。
3. 批量结果按 `巡检失败 / 需要处理 / 巡检正常` 分组后是否更容易扫读。
4. “下一步建议”是否有帮助，文案是否啰嗦。
5. 证据抽屉里的 `结论 / 证据 / 后续操作` 是否符合排查顺序。
6. 模板匹配入口放在批量摘要区是否容易找到。

## 下一步开发指示

### 如果用户确认切片 8 页面可用

先提交当前切片，再进入切片 9。

建议切片 9 方向：故障模板录入和模板匹配结果体验。

原因：

1. 自动巡检主流程已经具备基本可用性。
2. 用户最早提出的第二个核心能力是“录入故障模板并手动触发匹配”。
3. 现在模板匹配入口已有，但模板录入和结果解释还不够像运维诊断工具。

让 “故障模板与匹配引擎” 和 “前端工作台与人性化 UI” 分开处理，不要同时改同一文件。

### 切片 9A：让 “故障模板与匹配引擎” agent 处理

目标：

1. 优化模板匹配结果的解释能力。
2. 让每个模板结果说明“为什么命中 / 为什么未命中”。
3. 采集失败的模板要显示明确失败原因。
4. 保持当前 API 契约，优先复用 `template_match_results`。

边界：

1. 不改前端布局。
2. 不新增 AI 总结。
3. 不改 `TemplateConditionOperator`。
4. 不把完整 namespace inspection 结果塞进 diagnosis response。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
python3 -m pytest -q backend/tests
```

### 切片 9B：让 “前端工作台与人性化 UI” agent 处理

前置条件：

1. 等切片 9A 完成或确认不改后端响应结构。

目标：

1. 优化故障模板录入页的信息架构。
2. 模板目标、匹配条件、处理建议分区更清楚。
3. 模板匹配结果展示优先显示高置信命中。
4. 未命中模板默认收起或弱化，避免用户被大量无关模板淹没。

边界：

1. 不改后端 API。
2. 不改自动巡检页主流程。
3. 不删除模板导入导出，但应放在次级入口，不能占主操作区。

验收命令：

```bash
cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

### 如果用户认为切片 8 页面仍不好用

不要进入切片 9。

先让 “前端工作台与人性化 UI” 基于用户反馈返工，反馈至少要明确：

1. 哪个页面。
2. 哪个区块。
3. 当前哪里别扭。
4. 希望怎么操作。

返工时只改前端，不动后端 API 和健康语义。

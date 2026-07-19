# 切片 9 验收与下一步

## 验收结论

切片 9 验收通过。

本切片完成故障模板匹配结果体验增强，重点解决“模板匹配结果不像诊断结论、未命中模板铺满页面”的问题。

## 已确认能力

### 后端

1. `template_match_results[].summary` 不再只是“模板名 命中/未命中”。
2. 命中模板会返回解释性摘要，例如命中几个条件、哪些条件命中。
3. 未命中模板会返回缺失条件解释。
4. 采集失败模板会返回“无法判断”摘要。
5. 单模板采集失败不会拖垮整次 diagnosis。
6. 白名单日志仍不会参与模板命中。
7. 多 Pod 匹配仍保持“任一 Pod 命中即可”。
8. 未新增 diagnosis response 字段。

### 前端

1. 模板匹配结果总览展示：
   - 命中模板数
   - 未命中模板数
   - 无法判断模板数
2. 已命中模板优先展示且默认展开。
3. 无法判断模板单独展示，不混入普通未命中。
4. 未命中模板默认折叠，不再铺满页面。
5. 命中模板卡片突出：
   - 故障名称
   - 命中摘要
   - 判断原因
   - 建议动作
   - 风险说明
   - 命中条件
   - 关键证据
6. 自动巡检页、名称空间巡检页、独立诊断页的模板匹配入口都保留。

## 验证记录

已执行：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
cd frontend && npm test -- --run src/pages/DiagnosisPage.test.tsx src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端切片相关测试：14 passed
2. 前端切片相关测试：32 passed
3. 后端全量：87 passed
4. 前端全量：47 passed
5. 前端构建：通过

剩余警告：

1. 后端仍有 1 个既有 `Starlette/httpx` 弃用警告，和本切片无关。

## 当前建议

先构建镜像看真实模板匹配结果，不要马上继续扩新能力。

重点确认：

1. 命中的模板是否能一眼看懂“为什么命中”。
2. 未命中模板折叠后页面是否不再臃肿。
3. 无法判断模板是否足够醒目。
4. 建议动作是否有帮助。
5. 证据摘要是否足够支撑判断。

## 下一步开发指示

### 如果用户确认模板匹配结果体验可用

建议进入切片 10：故障模板录入页体验重构。

让 “前端工作台与人性化 UI” 先做，不要改后端。

目标：

1. 模板录入按步骤组织：
   - 基本信息
   - 目标范围
   - 匹配条件
   - 原因与建议
   - 预览与保存
2. 导入/导出放次级入口或弹窗。
3. 条件录入更贴近运维语言。
4. 多 target_ref、多条件 AND/OR 的关系更清楚。
5. 不让用户一开始面对一大堆表单。

边界：

1. 不改 matcher。
2. 不改 diagnosis response。
3. 不改巡检入口。
4. 不新增 AI 总结。

验收命令：

```bash
cd frontend && npm test -- --run src/pages/TemplatesPage.test.tsx src/pages/DiagnosisPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

### 如果用户认为模板匹配结果仍不好用

不要进入切片 10。

先基于用户反馈返工切片 9，只改 diagnosis 结果体验。

需要用户明确：

1. 哪个入口触发的模板匹配。
2. 看到哪些模板。
3. 哪段解释看不懂。
4. 希望优先看到什么。

返工边界：

1. 不扩 response 字段，除非已有字段无法表达。
2. 不把未命中模板重新默认铺开。
3. 不引入 AI 总结。

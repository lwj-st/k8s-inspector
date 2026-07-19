# 巡检入口信息架构重构验收与下一步

## 验收结论

本轮验收通过。

这轮解决的是“页面平铺、过长、主次不清”的信息架构问题，不是单纯 CSS 调整。

## 已确认能力

1. 名称空间巡检页以名称空间下拉为主入口。
2. 名称空间巡检页保留“高级手动输入”，但默认收起。
3. 名称空间巡检页不再常驻导入/导出 textarea。
4. 名称空间巡检页的保存、导入、导出都进入弹窗。
5. Pod 巡检页先选择名称空间，再选择巡检范围。
6. Pod 巡检范围支持：
   - `全部 Pod`
   - `Label Selector`
   - `单个 Pod`
7. `全部 Pod` 和 `Label Selector` 走 namespace inspection，展示多 Pod 范围结果。
8. `单个 Pod` 走 pod inspection，并使用 Pod 下拉选择。
9. Pod 下拉临时复用 namespace inspection 结果生成，没有扩后端 API。
10. 保存常用范围进入弹窗，文案改为“常用范围名称”。
11. 常用范围、编辑、删除放入次级区域，不再占据主流程。
12. 白名单忽略入口保留。
13. 模板匹配入口保留在名称空间巡检结果中。

## 验证记录

已执行：

```bash
cd frontend && npm test -- --run src/pages/NamespaceInspectionPage.test.tsx src/pages/PodInspectionPage.test.tsx src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 前端指定页面测试：35 passed
2. 前端全量测试：47 passed
3. 前端构建：通过

说明：

1. 本轮只改前端入口信息架构，未跑后端全量。
2. 后端 API、Pod 健康判定、故障模板 matcher 均未修改。

## 当前建议

先构建镜像看真实页面，不要继续叠新功能。

重点检查：

1. 名称空间巡检首屏是否能直接通过下拉选择 namespace。
2. Pod 巡检是否符合“先选 namespace，再选全部 Pod / Label Selector / 单个 Pod”的习惯。
3. 导入/导出是否只在弹窗出现。
4. 常用范围是否不再干扰主流程。
5. Label Selector 结果是否明确是范围巡检，不是单 Pod。
6. 单 Pod 下拉是否可用。

## 下一步指令

### 如果用户确认这轮页面结构可用

让 “故障模板与匹配引擎” 做切片 9A：模板匹配结果解释增强。

目标：

1. 每个模板结果说明“为什么命中 / 为什么未命中”。
2. 采集失败模板显示明确失败原因。
3. 保持当前 API 契约，优先复用 `template_match_results`。

边界：

1. 不改前端巡检入口。
2. 不改 Pod 健康判定。
3. 不新增 AI 总结。
4. 不把完整 namespace inspection 结果塞进 diagnosis response。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
python3 -m pytest -q backend/tests
```

### 如果用户认为入口仍不好用

不要进入切片 9。

让 “前端工作台与人性化 UI” 基于用户真实反馈返工，只改前端入口。

反馈必须具体到：

1. 哪个页面。
2. 哪个区块。
3. 当前看到什么。
4. 期望怎么操作。

返工仍禁止：

1. 不改后端 API。
2. 不改健康判定。
3. 不改故障模板 matcher。
4. 不把导入/导出 textarea 放回主页面。

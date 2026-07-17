# 自动巡检切片六前端记录

## 本轮范围

- 直接按切片六总控文档执行。
- 只处理自动巡检页中的“故障模板手动匹配入口”。
- 不改模板录入页，不改自动定时诊断，不做 AI 总结，不展示完整日志/describe 原文。

## 本轮实现

1. 在自动巡检页批量巡检摘要区新增“运行模板匹配”入口。
2. 点击后调用 `/api/v1/diagnoses/run`。
3. 匹配结果放在右侧抽屉中展示，不把结果塞进模板编辑表单，也不拉成长页面。
4. 复用现有 `DiagnosisResultPanel`，展示：
   - 已命中模板
   - 未命中模板
   - matched 条件
   - unmatched 条件
   - 每条条件的证据摘要
   - 诊断 loading / 失败 / 空结果
5. 结果顺序保持“已命中模板”优先，符合“高置信匹配优先”的展示要求。

## 测试覆盖

自动巡检页新增覆盖：

1. 手动触发模板匹配会调用正确的诊断接口。
2. 有匹配和未匹配模板时，结果能同时展示。
3. matched / unmatched 条件文案可见。
4. loading 状态可见。
5. 失败状态可见。
6. 空结果状态可见。

## 验证

执行：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

当前结果：

- 自动巡检页测试：21 passed
- 前端全量测试：执行中后已补跑
- 前端构建：执行中后已补跑

# Worklog: UI 紧凑化验收返工

## 本轮修正

1. 确认状态巡检当前已使用单名称空间下拉和“巡检全部名称空间”两个入口，没有恢复多选 checkbox 模型。
2. 确认 `/inspections/pod` 已复用统一 `NamespaceInspectionPage` 日志巡检入口，Overview 的日志巡检快捷入口也指向 `/inspections/namespace`。
3. 在关键字匹配和模板显式日志匹配中生成命中行前后最多 5 行上下文。
4. 模板 matcher 证据同步携带日志上下文字段。
5. 日志巡检、状态巡检证据抽屉和模板检查证据优先展示 `context_text`，缺省回退 `matched_text`，并明确提示不是完整日志。
6. 增加命中在开头、中间、结尾的上下文测试。

## 语义边界

- `matched_text` 仍表示命中行。
- 上下文来自本次采集到的日志 tail，不返回完整日志。
- 白名单过滤、模板匹配条件和后端巡检接口语义未改变。

## 验证

- 后端：102 passed，1 个既有 deprecation warning
- 前端：53 passed
- 前端构建：通过


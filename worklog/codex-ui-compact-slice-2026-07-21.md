# Worklog: UI 紧凑化改造阶段性实现

## 本轮完成

1. 完成 Label Selector discovery 的 Mock 与 Kubernetes provider 实现，按 `key=value` 聚合标签并统计 Pod 数量。
2. 新增 provider 异常的可读 502 响应和后端测试。
3. 导航收口为状态巡检、日志巡检、模板检查、故障模板、关键字库、系统配置六个入口；旧 Pod 路由继续保留兼容。
4. 日志、事件、Describe 摘要统一进入固定高度可滚动代码框。
5. 日志巡检页面接入 Label Selector 自动发现下拉，同时保留手动输入高级入口。
6. 关键字、白名单、故障模板摘要列表改为紧凑卡片，长文本使用省略和 title 提示。
7. 启用状态统一使用绿色，禁用状态使用灰色。

## 未改变

- 巡检请求参数和结果契约未改变。
- 关键字匹配和白名单过滤语义未改变。
- 故障模板 matcher 未改变。
- `/inspections/pod` 旧路由未删除。

## 验证

- 后端：98 passed
- 前端：55 passed
- 前端构建：通过


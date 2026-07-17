# 切片六模板目标过滤回修记录

## 复核结论

切片六已有诊断契约、matcher 和前端手动匹配入口。本轮发现一个范围缺口：模板 target 已支持 `pod_name_pattern`，但诊断采集后未按该模式过滤 Pod。

## 修改内容

- 诊断服务在构建模板 target context 时，按模板 target 的 `pod_name_pattern`/兼容字段 `name` 使用 shell 风格匹配过滤 Pod。
- namespace 和 label selector 仍由 provider 透传，未新增巡检 provider 或诊断接口。
- 补充测试，确保同一 namespace 中只有名称模式命中的 Pod 参与模板条件判断。

## 未修改范围

- 未改白名单和关键字管理。
- 未改自动巡检 UI。
- 未采集完整日志或 Describe。
- 未引入 AI、定时诊断和通知推送。

## 验证

- 后端全量：76 passed
- 前端全量：45 passed
- 前端 build：通过

# 自动巡检切片五验收结论与切片六开发指令

## 1. 切片五验收结论

切片五“日志关键字命中忽略与白名单闭环”已通过验收，可以进入切片六。

已确认完成：

1. 证据抽屉日志关键字命中旁提供“忽略此命中”。
2. 点击后先展示确认区域，不会静默提交。
3. 确认区域展示：
   - namespace
   - Label Selector
   - Pod
   - container
   - keyword
4. 前端调用 `/api/v1/whitelists/ignore`，payload 字段正确。
5. 成功后当前抽屉内该命中显示“已忽略”。
6. 已白名单命中按钮禁用。
7. 创建失败时抽屉保持打开并展示错误。
8. 后端白名单匹配覆盖：
   - namespace
   - label_selector
   - pod_name_pattern
   - container_name
   - keyword
   - enabled
9. 禁用白名单后，命中恢复为 `whitelisted=false`。
10. batch summary 中 `log_keyword` 只由未白名单日志命中触发。
11. 全部日志命中都已白名单时，batch summary 不再包含 `log_keyword`。
12. 已白名单日志命中仍保留在 namespace 详情结果中，供前端展示“已忽略”。

验证命令：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_whitelist_api.py
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

验证结果：

1. 后端巡检/白名单重点测试：30 passed，1 warning。
2. 后端全量测试：72 passed，1 warning。
3. 前端全量测试：37 passed。
4. 前端生产构建：通过。

注意：

`worklog/codex-keyword-whitelist-slice-5-rework-2026-07-17.md` 中提到“后端全量未绿”的内容已过期，以本验收文档的实测结果为准。

## 2. 切片六目标

切片六只做“故障模板手动匹配入口”。

用户已经能自动巡检 namespace 并查看证据。下一步应能手动触发故障模板匹配，判断当前异常是否符合某个已录入故障模板。

本切片目标：

1. 用户在自动巡检页或模板页手动触发模板匹配。
2. 系统按模板中配置的 namespace、label、Pod 匹配条件进行检查。
3. 模板条件可以组合多个来源：
   - Pod 状态
   - 日志关键字命中
   - event 关键字
   - restart_count
   - 关联对象状态
4. 多个 Pod 匹配时，只要任一 Pod 满足条件即可视为该条件匹配。
5. 输出匹配结果时要能说明：
   - 哪些条件匹配
   - 哪些条件未匹配
   - 证据摘要
   - 匹配置信息

本切片仍然不做：

1. 自动定时诊断。
2. 告警推送。
3. 完整日志原文。
4. 完整 describe 原文。
5. AI 总结。
6. 模板批量导入导出 UI 优化。

## 3. 给“统一契约与数据模型”的指令

让“统一契约与数据模型” agent 先复核当前故障模板匹配契约是否足够。

重点检查：

1. `FaultTemplate`
2. `TemplateTarget`
3. `TemplateCondition`
4. `DiagnosisRequest`
5. `DiagnosisResponse`
6. `matched_conditions`
7. `unmatched_conditions`
8. `evidence_summary`

必须确认：

1. 是否支持模板目标中指定 namespace 与 label selector。
2. 是否支持一个模板包含多个 target group。
3. 是否支持同一条件匹配多个 Pod 时“任一 Pod 命中即可”。
4. 前端类型是否覆盖后端枚举。
5. 诊断响应是否足够前端展示匹配与未匹配原因。

如果现有契约足够，不要新增字段。

只有在缺少必要展示字段时，才允许最小补充。

禁止事项：

1. 不改巡检契约。
2. 不把完整 namespace 巡检详情塞进诊断响应。
3. 不新增 AI 总结字段。

验收标准：

1. 契约文档写清楚模板匹配的输入、输出、边界。
2. 后端契约测试通过。
3. 前端类型与后端 schema 对齐。

## 4. 给“故障模板与匹配引擎”的指令

让“故障模板与匹配引擎” agent 检查并补齐模板匹配能力。

目标文件优先看：

1. `backend/app/engine/matcher.py`
2. `backend/app/services/diagnosis_service.py`
3. `backend/tests/test_matcher.py`
4. `backend/tests/test_diagnosis_api.py`
5. `backend/tests/test_template_api.py`

必须保证：

1. `log_keyword` 只消费 `whitelisted=false` 的 `KeywordHit`。
2. `pod_status` 支持模板中指定的状态匹配。
3. `restart_count` 支持 `gte/lte/eq` 等现有操作符。
4. `event_keyword` 支持 event 文本匹配。
5. `related_object_status` 支持 Service、Ingress、DaemonSet、TLS Secret 等对象状态匹配。
6. 当目标范围内匹配多个 Pod 时，任一 Pod 满足条件即可。
7. 多个条件按模板配置的 AND/OR 规则计算。
8. 未匹配条件要返回可读原因或至少保留原条件。

禁止事项：

1. 不做前端 UI。
2. 不改自动巡检页。
3. 不采集完整日志。
4. 不引入 AI 判断。

验收标准：

1. 单条件匹配测试通过。
2. 多条件 AND/OR 匹配测试通过。
3. 多 Pod 任一命中测试通过。
4. 白名单日志命中不参与模板匹配测试通过。
5. 关联对象状态匹配测试通过。
6. 后端全量测试通过。

## 5. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 确认诊断入口如何采集模板匹配所需证据。

必须保证：

1. 诊断服务按模板目标采集对应 namespace。
2. 采集时透传模板中的 label selector。
3. 诊断服务复用已有 namespace 巡检结果结构。
4. 诊断服务返回的 `evidence_summary` 来自真实匹配证据。
5. 单个模板采集失败时，不应导致所有模板结果不可用，除非当前接口设计明确只支持整体失败。

禁止事项：

1. 不新增重复巡检 provider。
2. 不把模板逻辑塞进 K8s provider。
3. 不做前端。

验收标准：

1. API 测试覆盖按模板 target namespace/label 采集。
2. API 测试覆盖多个模板时的成功/失败边界。
3. 后端全量测试通过。

## 6. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 在后端契约稳定后实现手动模板匹配入口。

推荐入口：

1. 自动巡检页的批量结果区增加“模板匹配”入口。
2. 模板页保留模板管理，但不要把诊断结果塞进模板编辑表单。
3. 诊断结果用抽屉或紧凑面板展示，不要新增长页面。

必须展示：

1. 匹配到的模板。
2. 未匹配模板。
3. 每个模板的 matched/unmatched 条件。
4. 每条条件的证据摘要。
5. 诊断运行状态、失败状态、空状态。

UI 要求：

1. 不展示完整日志原文。
2. 不展示完整 describe 原文。
3. 条件结果要用中文解释，避免只暴露枚举。
4. 匹配结果要按“高置信匹配优先”展示。
5. 用户能快速看出“是不是这个故障”。

禁止事项：

1. 不做 AI 总结。
2. 不做自动定时诊断。
3. 不做通知推送。
4. 不重构模板录入页。

验收标准：

1. 前端测试覆盖手动触发模板匹配。
2. 前端测试覆盖有匹配、无匹配、失败、loading。
3. 前端测试覆盖 matched/unmatched 条件展示。
4. 前端全量测试和 build 通过。

## 7. 给“关键字库与白名单”的指令

本切片只做回归验证。

必须确认：

1. 模板匹配不使用 `whitelisted=true` 的日志命中作为有效证据。
2. 一键忽略后，相关日志条件不会误匹配。

禁止事项：

1. 不改白名单 UI。
2. 不改关键字管理。

## 8. 给“K8s 采集与证据抽取”的指令

本切片默认不需要开发。

只有在模板匹配发现缺少 event 或关联对象状态字段时，才允许最小补齐。

禁止事项：

1. 不扩展完整日志。
2. 不把模板判断写进 provider。

## 9. 推荐执行顺序

1. 先让“统一契约与数据模型”复核诊断契约。
2. 再让“故障模板与匹配引擎”补齐 matcher 单元测试和逻辑。
3. 再让“巡检编排与检查入口”补齐诊断 API 采集与返回。
4. 最后让“前端工作台与人性化 UI”实现手动模板匹配入口。
5. “关键字库与白名单”和“K8s 采集与证据抽取”只在发现对应缺口时介入。


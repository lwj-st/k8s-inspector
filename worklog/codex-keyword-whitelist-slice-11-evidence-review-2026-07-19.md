# Worklog: 切片 11 关键字库与白名单证据复核

## 复核范围

- `frontend/src/pages/AutoInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- mock/provider 巡检证据结构

## 结论

现有巡检证据字段足够支撑关键字与白名单页面的解释性要求：

1. Pod 证据包含状态、异常分类、事件摘要和 `describe_summary`。
2. 日志证据包含关键字、类别、严重级别、匹配文本和容器名称。
3. 日志命中包含 `whitelisted` 与 `whitelist_rule_id`，可以区分命中但被忽略的报错。
4. 巡检证据抽屉和 Pod 巡检页面都提供“忽略此报错”入口，并将规则写入统一白名单。
5. 白名单管理页复用 `note` 展示来源说明，不需要新增来源字段。

## 边界

本次未修改证据 schema、provider、日志采集或巡检流程，仅完成只读复核。


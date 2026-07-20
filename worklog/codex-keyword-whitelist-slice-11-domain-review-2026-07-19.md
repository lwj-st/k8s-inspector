# Worklog: 切片 11 关键字库与白名单领域复核

## 复核范围

- `backend/app/services/keyword_service.py`
- `backend/app/services/whitelist_service.py`
- 关键字、白名单 API 与现有后端测试

## 结论

当前领域实现已经满足页面体验收口，不需要新增字段或修改语义：

1. 只有启用的关键字规则参与日志匹配，匹配仍为不区分大小写的包含关系。
2. 白名单仍按名称空间、Label Selector、Pod 名称模式、容器名称和关键字逐项过滤；未填写的范围字段继续表示不限定该范围。
3. 白名单命中后保留 `whitelisted` 和 `whitelist_rule_id`，页面可解释“为何忽略”。
4. “忽略此报错”创建的规则复用同一套白名单字段和匹配逻辑。
5. 导入、导出、启停和删除接口均已有实现，切片 11 不需要扩展后端。

## 边界

本次未修改关键字匹配、白名单过滤、巡检主流程或 provider。


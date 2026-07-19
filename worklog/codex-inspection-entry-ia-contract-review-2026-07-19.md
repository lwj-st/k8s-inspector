# 巡检入口 IA 契约复核

## 结论

现有接口足够支撑下拉式巡检入口，不新增后端 API 或字段。

- `GET /discovery/namespaces` 用于名称空间下拉。
- `POST /inspections/namespace/run` 支持全名称空间和 Label Selector 范围巡检。
- namespace 巡检结果中的 `pods` 可临时生成单 Pod 下拉选项。
- `POST /inspections/pod/run` 仅用于单 Pod 精确巡检。
- 保存范围、导入导出接口已存在，可由前端放入弹窗。

本轮未修改契约、健康判定和后端接口。

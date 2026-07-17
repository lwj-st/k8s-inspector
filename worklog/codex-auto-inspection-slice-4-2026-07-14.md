# 自动巡检切片四实现记录

## 契约与接口确认

- 复用批量结果中的 `detail_target.namespace`。
- 复用 `POST /api/v1/inspections/namespace/run` 获取 namespace 详情。
- 未修改 batch response，也未新增详情接口。
- 现有 `NamespaceInspectionResponse`、`InspectedPod`、`EvidenceBundle` 和 `KeywordHit` 足够支撑下钻。

## 实现内容

- 自动巡检批量结果卡片新增“查看证据”。
- 使用右侧详情面板展示 namespace 状态、Pod 数量和异常分类对应的证据。
- 异常 Pod 默认展示，正常 Pod 收纳在折叠区域。
- Pod 证据展示状态、重启次数、节点、容器状态/reason、事件摘要、Describe 摘要、日志关键字命中和关联对象。
- 增加 loading、空结果和失败提示。
- 不展示完整日志、完整 Describe，不增加白名单、模板、导入导出和保存巡检对象能力。

## 验证

- 后端重点测试：24 passed
- 前端自动巡检页测试：13 passed
- 前端全量测试与 build：随后执行

## 2026-07-17 切片四返工补充

- 本轮没有额外疑问，直接按总控返工指令处理前端。
- `查看证据` 改为接收完整 batch result，不再只传 `summary`。
- 详情请求改为优先使用 `detail_target.namespace`，并透传 `detail_target.label_selector`；无值时传 `null`。
- 证据抽屉顶部补充异常分类中文标签。
- 证据抽屉补充 namespace 级对象摘要：
  - `Service`
  - `Ingress`
  - `DaemonSet`
  - `TLS Secret`
- namespace 级对象按异常优先展示；正常对象折叠弱化，避免主视图继续拉长。
- 补充测试覆盖：
  - `detail_target.namespace` 与 `summary.name` 不一致时，详情请求仍使用 `detail_target.namespace`
  - `detail_target.label_selector` 透传
  - 抽屉顶部异常分类展示
  - Pod 全部正常但 `Ingress/DaemonSet` 异常时，抽屉仍展示真实异常对象

## 2026-07-17 验证

- `cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx`：14 passed
- `cd frontend && npm test -- --run`：34 passed
- `cd frontend && npm run build`：已重新执行

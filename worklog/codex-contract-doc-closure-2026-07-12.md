# Worklog: 契约文档收口

## 时间

- 日期：2026-07-12
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 21 节，只修正文档中的契约描述，不改代码。

## 修改内容

本轮只修改了：

- `docs/superpowers/plans/2026-07-11-api-contract.md`

具体修正了 3 处说明：

1. `TemplateTarget` 直接兼容输入
- 明确补充：
  - `ref -> target_ref`
  - `name -> pod_name_pattern`
  - `scopes -> resource_scope`

2. `object_scope` 在 `TemplateTarget` 上的语义
- 明确：
  - `object_scope` 不是 `TemplateTarget` 的直接输入 alias
  - `object_scope` 是计算输出
  - 其值取 `resource_scope[0]`

3. `FaultTemplate.target_groups` 的兼容归一化
- 明确：
  - `target_groups` 兼容输入可以使用 `ref/name/object_scope`
  - 其中 `object_scope` 会在 `FaultTemplate` 归一化阶段转换为 `targets[].resource_scope`

## 是否改动代码

没有。

本轮未改动：

- 后端 schema
- 前端类型
- 前端 client
- 测试代码

## 当前结论

本轮属于文档级收口：

- 代码契约未变
- 文档描述已与当前实现保持一致

## 是否仍存在契约歧义

本轮处理后，`TemplateTarget` 与 `FaultTemplate.target_groups` 这部分的层级说明已清楚。

当前剩余风险不在本轮范围内：

- 业务语义风险
- 多模块集成风险

这些应继续交给后续“整体质量验收”关注。

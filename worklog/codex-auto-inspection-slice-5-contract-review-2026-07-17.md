# Worklog: 自动巡检切片五契约复核

## 时间

- 日期：2026-07-17
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-17-auto-inspection-slice-4-acceptance-and-slice-5-instructions.md` 第 3 节，只复核“从日志命中一键忽略”的白名单契约，不做 UI，不做白名单过滤实现。

## 复核结论

现有后端白名单契约已经足够支撑“一键忽略”，无需新增后端字段或重复模型。

已确认可直接复用：

1. `KeywordHit`
2. `WhitelistCreate`
3. `WhitelistRead`
4. `WhitelistIgnoreCreate`
5. `namespace`
6. `label_selector`
7. `pod_name_pattern`
8. `container_name`
9. `keyword`
10. `enabled`
11. `note`

## 本轮最小收口

虽然字段本身已足够，但前端之前没有把白名单请求体抽成共享类型，而是直接写在 `api/client.ts` 中。

本轮做了最小同步：

1. 在 `frontend/src/api/types.ts` 中补齐：
   - `WhitelistCreate`
   - `WhitelistIgnoreCreate`
2. 在 `frontend/src/api/client.ts` 中改为直接复用这两个类型。
3. 在契约文档中明确一键忽略默认生成的白名单字段和默认范围。

## 一键忽略默认范围

推荐默认范围：

- `namespace + pod_name_pattern + container_name + keyword`

补充规则：

- 如果当前巡检来自 `detail_target.label_selector`，白名单请求同时带上该 `label_selector`
- `pod_name_pattern` 当前默认可直接使用当前 Pod 名
- `note` 默认写入来源说明，例如“自动巡检证据抽屉忽略”

## 刻意没做

- 没有新增后端 schema 字段
- 没有新增重复白名单模型
- 没有把白名单逻辑塞进模板模型
- 没有改导入导出
- 没有改 UI

## 验证结果

已执行：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

- 后端契约测试通过
- 前端测试通过
- 前端 build 通过

## 对后续 agent 的边界说明

1. 后端白名单闭环应继续复用 `/api/v1/whitelists/ignore` 或既有白名单创建能力。
2. 前端证据抽屉不要再自定义另一套忽略 payload。
3. 后续如要支持通配规则编辑，应在 UI 层扩展，不要先改本轮基础契约。

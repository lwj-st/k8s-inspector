# Worklog: K8s 采集与证据抽取

## 时间

- 日期：2026-07-11
- Agent：Codex

## 本次目标

完成《K8s 采集与证据抽取》任务，并确认相关后端能力可运行、可测试、可供其他 agent 继续协同。

## 已完成内容

1. 补齐巡检证据结构
- 名称空间巡检的 `pods` 结果已包含：
  - `node_name`
  - `containers`
  - `describe_summary`
  - `log_summary`
  - `previous_log_summary`
  - `related_resources`
  - `log_hits`

2. 补齐 Pod 巡检链路
- 新增接口：
  - `POST /api/v1/inspections/pod/run`
  - `GET /api/v1/inspections/pod/history`

3. 补齐统一巡检分发
- 新增接口：
  - `POST /api/v1/inspections/run`

4. 补齐诊断上下文抽取
- `collect_diagnosis_context` 已支持按 `scope` 过滤 Pod
- 模板检查不再把无关 Pod 一起带入上下文

5. 补齐关键字命中证据串联
- 巡检结果已串上 `log_hits`
- 白名单命中状态可体现在 `log_hits[].whitelisted`

6. 补齐模板匹配基础引擎
- 支持：
  - `pod_status`
  - `log_keyword`
  - `event_keyword`
  - `restart_count`
  - `related_object_status`
- 输出：
  - `matched_conditions`
  - `unmatched_conditions`
  - `evidence`

7. 补齐缺失源码文件
- 新增：
  - `backend/app/engine/matcher.py`
  - `backend/app/schemas/diagnosis.py`
- 这一步很关键，否则新会话里可能只剩 `pyc`，测试会不稳定

## 主要涉及文件

- `backend/app/providers/base.py`
- `backend/app/providers/kubernetes_provider.py`
- `backend/app/providers/mock_provider.py`
- `backend/app/services/inspection_service.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/api/routes/inspections.py`
- `backend/app/engine/matcher.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/common.py`
- `backend/tests/test_inspection_api.py`
- `backend/tests/test_kubernetes_provider.py`

## 验证结果

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/backend
python3 -m pytest -q tests
```

结果：

- `29 passed`

## 当前结论

《K8s 采集与证据抽取》这项任务当前已完成，后端回归已通过。

## 交接说明

1. 当前仓库还有其他未完成工作
- `saved_targets`
- 前端页面与测试
- 其他 agent 的并行改动

这些不属于本次《K8s 采集与证据抽取》收口范围，不建议在后续 agent 里把它们和本任务混在一起处理。

2. 后续 agent 可以直接依赖的能力
- `namespace` 巡检接口
- `pod` 巡检接口
- 统一巡检分发接口
- `log_hits`
- `evidence_bundle / evidence_bundles`
- 模板匹配明细

3. 建议后续优先衔接的任务
- 前端工作台接入 `pod` 巡检和证据详情
- 保存巡检对象 `saved_targets`
- 模板录入页和模板检查结果页联调

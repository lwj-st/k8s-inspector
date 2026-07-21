# 2026-07-21 UI 大调整主会话验收与返工指令

## 验收结论

本轮代码测试通过，但产品验收未完全通过。

已通过：

1. 后端测试通过。
2. 前端测试通过。
3. 前端构建通过。
4. 导航主入口已改为 `状态巡检`、`日志巡检`、`模板检查`、`故障模板`、`关键字库`、`系统配置`。
5. `日志巡检` 已合并全部 Pod、Label Selector、单个 Pod 三种巡检模式。
6. Label Selector 自动发现接口和前端下拉已接入。
7. 故障模板、关键字库、白名单、导入导出弹窗已明显紧凑化。

未通过：

1. `状态巡检` 页面仍把名称空间列表以多选列表方式展示，仍保留 `全选当前结果`、`取消当前结果`、`巡检选中` 这种多选批量模型，不符合用户要求的“巡检全部名称空间，或者单独选名称空间巡检”。
2. `日志巡检` 日志命中仍只展示 `hit.matched_text`，没有实现“命中关键字上下 5 行”的上下文展示。
3. `/inspections/pod` 旧路由仍直接进入 `PodInspectionPage` 的默认单 Pod 模式，不是重定向或复用统一 `日志巡检` 默认入口。
4. `OverviewPage` 的 `日志巡检` 快捷入口仍指向 `/inspections/pod`，会继续强化旧的单 Pod 入口路径。

## 已执行验证

```bash
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

结果：

1. 后端：98 passed，1 个既有 Starlette/httpx deprecation warning。
2. 前端测试：53 passed。
3. 前端构建：通过。

## 给 “前端工作台与人性化 UI” agent 的返工任务一：状态巡检入口必须收口

参考文件：

1. `frontend/src/pages/AutoInspectionPage.tsx`
2. `frontend/src/pages/AutoInspectionPage.test.tsx`
3. `frontend/src/styles.css`

问题位置：

1. `frontend/src/pages/AutoInspectionPage.tsx` 中仍存在 `名称空间列表`。
2. 页面仍通过 checkbox 支持多选名称空间。
3. 页面仍有 `全选当前结果`、`取消当前结果`、`巡检选中`。

必须改成：

1. 顶部只保留两个主操作：
   - `巡检全部名称空间`
   - `选择一个名称空间` 下拉框 + `巡检该名称空间`
2. 名称空间不要以列表铺出来。
3. 如果需要搜索名称空间，只能作为下拉框过滤能力，不要在主页面显示完整名称空间列表。
4. 删除多选状态和多选操作：
   - `selectedNamespaces`
   - checkbox 列表
   - `全选当前结果`
   - `取消当前结果`
   - 多选数量指标
5. 单名称空间巡检可以继续复用 `runNamespaceBatchInspection({ namespaces: [namespace], all_namespaces: false })`，也可以复用已有单 namespace inspection，但页面语义必须是“单选”。
6. 批量结果仍可用紧凑表格/滚动容器展示，但那是巡检结果，不是待选名称空间列表。

边界：

1. 不改后端接口。
2. 不恢复名称空间导入导出。
3. 不把状态巡检做成日志巡检页面。

验收：

1. 未巡检时，状态巡检页面不能出现完整名称空间列表。
2. 页面只能选一个名称空间或巡检全部。
3. 测试必须断言旧的多选操作不存在。

## 给 “前端工作台与人性化 UI” agent 的返工任务二：旧 Pod 路由收口

参考文件：

1. `frontend/src/routes/index.tsx`
2. `frontend/src/pages/OverviewPage.tsx`
3. `frontend/src/pages/PodInspectionPage.tsx`
4. `frontend/src/app/App.test.tsx`
5. `frontend/src/routes/basePath.test.tsx`

必须改成：

1. `/inspections/namespace` 作为统一 `日志巡检` 主入口。
2. `/inspections/pod` 不能再作为事实上的“单 Pod 默认入口”。
3. 推荐做法：
   - `/inspections/pod` 重定向到 `/inspections/namespace`
   - 或让 `/inspections/pod` 渲染同一个 `日志巡检` 页面，但默认也不要强调旧入口
4. `OverviewPage` 的 `日志巡检` 快捷入口必须指向 `/inspections/namespace`。
5. `PodInspectionPage` 内部按钮文案可以保留 `巡检单个 Pod`，因为这是日志巡检页面内的范围模式，不是导航入口。

边界：

1. 不删除单个 Pod 巡检能力。
2. 不改后端 Pod 巡检接口。
3. 不增加新的导航项。

验收：

1. 导航中没有 `单 Pod 巡检`。
2. 总览快捷入口不再跳到 `/inspections/pod`。
3. 直接访问 `/inspections/pod` 不会形成独立旧入口体验。

## 给 “统一契约与数据模型” agent 的任务：日志命中上下文契约设计

参考文件：

1. `backend/app/schemas/common.py`
2. `backend/app/services/keyword_service.py`
3. `backend/app/services/inspection_service.py`
4. `backend/app/services/diagnosis_service.py`
5. `frontend/src/api/types.ts`
6. `docs/superpowers/plans/2026-07-11-api-contract.md`

问题：

当前 `KeywordHit` 只有：

1. `keyword`
2. `matched_text`
3. `container_name`
4. 白名单等元数据

这只能展示命中行，无法可靠展示“命中关键字上下 5 行”。

任务：

1. 设计日志命中上下文字段。
2. 推荐在 `KeywordHit` 增加可选字段：
   - `context_before: string[]`
   - `context_after: string[]`
   - `context_text: string | null`
3. 字段必须可选，避免破坏旧 mock 和旧接口。
4. 明确上下文来自本次采集到的容器日志 tail，不代表完整日志。
5. 前后端类型必须一致。

边界：

1. 不改变 `matched_text` 语义。
2. 不要求返回完整日志。
3. 不把上下文直接放进模板条件。

验收：

1. 契约文档更新。
2. 后端 schema 与前端 type 对齐。
3. 测试覆盖缺省字段兼容。

## 给 “K8s 采集与证据抽取” agent 的任务：生成日志命中上下文

必须等待 “统一契约与数据模型” agent 完成上下文契约后再做。

参考文件：

1. `backend/app/services/keyword_service.py`
2. `backend/app/services/inspection_service.py`
3. `backend/app/services/diagnosis_service.py`
4. `backend/tests/test_whitelist_api.py`
5. `backend/tests/test_inspection_api.py`
6. `backend/tests/test_diagnosis_api.py`

任务：

1. 在匹配关键字时，从当前容器日志中提取命中行上下 5 行。
2. 对系统关键字和模板显式日志关键字都要生效。
3. 多次命中同一关键字时，先返回第一处命中的上下文即可。
4. 白名单命中仍保留上下文，但 UI 可弱化展示。

边界：

1. 不返回完整日志。
2. 不改变白名单判断维度。
3. 不改变模板 matcher 的命中语义。

验收：

1. `KeywordHit.matched_text` 仍是命中行。
2. 新增上下文字段包含命中行前后最多 5 行。
3. 后端测试覆盖：
   - 命中在中间
   - 命中在开头
   - 命中在结尾
   - 多容器命中

## 给 “前端工作台与人性化 UI” agent 的返工任务三：展示日志上下文

必须等待上下文契约和后端生成完成。

参考文件：

1. `frontend/src/pages/PodInspectionPage.tsx`
2. `frontend/src/features/diagnosis/DiagnosisResultPanel.tsx`
3. `frontend/src/api/types.ts`
4. `frontend/src/pages/PodInspectionPage.test.tsx`
5. `frontend/src/pages/DiagnosisPage.test.tsx`

任务：

1. 日志命中卡片中优先展示 `context_text`。
2. 如果没有 `context_text`，再 fallback 到 `matched_text`。
3. 代码框必须可滚动。
4. UI 文案要说明“展示命中上下文，不是完整日志”。
5. 模板检查证据详情也要展示上下文，而不是只展示 JSON。

边界：

1. 不展示完整日志。
2. 不让日志上下文撑开页面。
3. 不破坏白名单忽略按钮。

验收：

1. 日志巡检中关键字命中可看到上下文代码框。
2. 模板检查中命中日志证据可看到上下文代码框。
3. 长上下文不会撑高页面。

## 主会话下一次验收重点

下一轮完成后，主会话重点检查：

1. `状态巡检` 未巡检状态下是否仍展示名称空间列表。
2. 是否还存在多选名称空间模型。
3. `/inspections/pod` 是否仍形成独立旧入口。
4. 日志命中是否真的展示上下 5 行上下文。
5. 后端、前端测试和构建是否通过。

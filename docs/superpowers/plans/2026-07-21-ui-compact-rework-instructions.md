# 2026-07-21 UI 大调整任务指令

## 背景

用户反馈当前 UI 的核心问题不是功能缺失，而是页面组织方式不符合巡检使用习惯：

1. 页面太长，所有内容平铺，主次不清。
2. 名称空间列表、关键字列表、保存范围、模板表单等卡片过大，导致需要一直向下滚动。
3. 日志、事件、describe 没有统一放进可滚动代码框。
4. 自动巡检、名称空间巡检、Pod 巡检的导航和职责混乱。
5. Label Selector 应该能自动发现并下拉选择，不应要求用户手工记忆。
6. 弹窗、按钮、启用状态、导入导出样式不够精致。

本轮目标是做 UI 信息架构和密度重构，不是继续堆功能。

## 总体产品目标

最终导航调整为：

1. `状态巡检`
2. `日志巡检`
3. `模板检查`
4. `故障模板`
5. `关键字库`
6. `系统配置`

页面职责：

1. `状态巡检`：只做名称空间级状态巡检，支持巡检全部名称空间或选择单个名称空间，不再把所有名称空间大卡片平铺出来。
2. `日志巡检`：合并原 `名称空间巡检` 和 `单 Pod 巡检`，支持选择名称空间后，对全部 Pod、Label Selector 范围、单个 Pod 做日志/describe/事件检查。
3. `模板检查`：重点展示命中了哪些故障模板。未命中模板默认折叠，详细日志、describe、条件证据都必须点进去看。
4. `故障模板`：负责模板录入、编辑、导入导出。UI 要紧凑、精致、易读。
5. `关键字库`：负责系统关键字和白名单。列表要高密度，不能一个关键字占一大块。

## 全局 UI 约束

所有前端 agent 必须遵守：

1. 页面不能无限向下增长，主页面首屏必须看清主要操作入口和当前结果摘要。
2. 大列表必须使用紧凑表格、分组列表、抽屉、折叠区或固定高度滚动容器。
3. 日志、事件、describe、JSON、命令必须使用代码框展示，代码框必须支持滚动。
4. 匹配到关键字时，默认展示命中行上下 5 行；不要把全量日志直接撑开页面。
5. 长文本默认单行省略或限制高度，鼠标悬停可看完整内容，必要时提供复制按钮。
6. 导入导出必须是弹窗或抽屉，不允许占用主页面固定空间。
7. 弹窗表单字段要对齐，输入框可适当变大，按钮要小而明确，圆角统一。
8. 启用状态使用绿色视觉；禁用使用灰色。
9. 按钮不允许又宽又大地占满整行，除非是页面唯一主操作。
10. 修改 UI 时必须同步更新前端测试，不允许只改页面不改测试。

## 执行顺序

第一阶段必须串行：

1. 让 “统一契约与数据模型” agent 先补 Label Selector 自动发现契约。
2. 让 “K8s 采集与证据抽取” agent 实现 Label Selector 自动发现接口。
3. 让 “前端工作台与人性化 UI” agent 建立公共紧凑 UI 样式和导航结构。

第二阶段可并行：

1. “前端工作台与人性化 UI” agent 改 `状态巡检` 和 `日志巡检`。
2. “故障模板与匹配引擎” agent 改 `模板检查` 展示重点。
3. “关键字库与白名单” agent 改 `关键字库` 页面密度和弹窗。

第三阶段串行：

1. 让 “统一契约与数据模型” agent 做契约复核。
2. 让 “前端工作台与人性化 UI” agent 做整体 UI 回归和测试修正。
3. 由主会话验收并决定是否提交。

## 给 “统一契约与数据模型” agent 的任务

参考文件：

1. `frontend/src/api/types.ts`
2. `backend/app/schemas/inspection.py`
3. `backend/app/api/routes/discovery.py`
4. `backend/app/services/discovery_service.py`
5. `backend/app/providers/base.py`
6. `docs/superpowers/plans/2026-07-11-api-contract.md`

任务：

1. 设计 `Label Selector` 自动发现契约。
2. 推荐新增接口：`GET /api/v1/discovery/namespaces/{namespace}/labels`。
3. 返回结构建议：

```json
{
  "namespace": "platform",
  "executed_at": "2026-07-21T00:00:00Z",
  "labels": [
    {
      "key": "app.kubernetes.io/instance",
      "values": ["lazy-rag-file-process-worker"],
      "selector": "app.kubernetes.io/instance=lazy-rag-file-process-worker",
      "pod_count": 3
    }
  ]
}
```

边界：

1. 不要改巡检结果主契约。
2. 不要把 Label Selector 存成用户配置。
3. 不要要求名称空间巡检导入导出。
4. 只做契约、类型、文档和测试约束。

验收：

1. 后端 schema 和前端 type 对齐。
2. 新接口响应字段明确，不使用宽松 `any`。
3. 文档说明 Label Selector 是“自动发现候选项”，不是强制范围。

## 给 “K8s 采集与证据抽取” agent 的任务

参考文件：

1. `backend/app/providers/kubernetes_provider.py`
2. `backend/app/providers/mock_provider.py`
3. `backend/app/providers/base.py`
4. `backend/app/services/discovery_service.py`
5. `backend/app/api/routes/discovery.py`
6. `backend/tests/test_discovery_api.py`

任务：

1. 实现名称空间下 Pod label 自动发现。
2. 统计每个 `key=value` 对应的 Pod 数量。
3. 返回可直接用于巡检的 `selector` 字符串。
4. Mock provider 也要有稳定数据，保证前端测试可用。

边界：

1. 不要改实际巡检逻辑。
2. 不要把 label 自动发现做成保存对象。
3. 不要在后端替用户选择默认 label。
4. 不要返回过大的原始 Pod 列表，只返回 label 候选摘要。

验收：

1. `GET /api/v1/discovery/namespaces/{namespace}/labels` 可用。
2. 空名称空间返回空 labels，不报 500。
3. K8s API 异常要返回可理解错误，不导致整个应用崩溃。
4. 后端测试覆盖正常、空列表、异常场景。

## 给 “前端工作台与人性化 UI” agent 的任务一：公共 UI 和导航

参考文件：

1. `frontend/src/layouts/AppLayout.tsx`
2. `frontend/src/routes/index.tsx`
3. `frontend/src/styles.css`
4. `frontend/src/app/App.test.tsx`
5. `frontend/src/routes/basePath.test.tsx`

任务：

1. 修改导航名：
   - `/`：`状态巡检`
   - `/inspections/namespace` 或新路由：`日志巡检`
   - `/diagnosis`：`模板检查`
   - `/templates`：`故障模板`
   - `/whitelists`：`关键字库`
   - `/settings`：`系统配置`
2. 合并原 `单 Pod 巡检` 入口到 `日志巡检`，导航不再展示单独 `单 Pod 巡检`。
3. 可保留 `/inspections/pod` 路由兼容旧地址，但必须重定向或复用 `日志巡检` 页面，不再作为独立导航。
4. 建立公共样式：
   - `.compact-card`
   - `.compact-table`
   - `.code-block-scroll`
   - `.ellipsis-cell`
   - `.mini-button`
   - `.status-toggle-enabled`
   - `.modal-card-polished`
5. 统一弹窗视觉：最大宽度、圆角、阴影、按钮区域、表单网格。

边界：

1. 不要改后端 API。
2. 不要重写所有页面业务逻辑。
3. 不要删除旧测试，只调整断言文案和可访问名称。

验收：

1. 导航不再出现 `自动巡检`、`名称空间巡检`、`单 Pod 巡检`。
2. 首屏导航清晰，不出现长按钮列表。
3. 前端测试通过。

## 给 “前端工作台与人性化 UI” agent 的任务二：状态巡检页面

参考文件：

1. `frontend/src/pages/AutoInspectionPage.tsx`
2. `frontend/src/pages/AutoInspectionPage.test.tsx`
3. `frontend/src/features/inspections/useDiscoverNamespaces.ts`
4. `frontend/src/features/inspections/useRunNamespaceInspection.ts`

任务：

1. 页面标题改为 `状态巡检`。
2. 操作入口只保留：
   - `巡检全部名称空间`
   - 名称空间下拉框 + `巡检选中名称空间`
3. 名称空间列表不能以大卡片平铺展示。
4. 名称空间候选使用下拉框或紧凑选择器；如果要展示结果列表，必须是固定高度紧凑表格。
5. 批量结果按健康状态分组，但每组默认最多展示固定高度，超出滚动。
6. 点击某个名称空间后，用抽屉或详情面板展示摘要，不把所有 Pod 详情直接铺开。
7. 模板匹配入口保留，但不要抢占状态巡检主流程。

边界：

1. 状态巡检页面不负责全量日志阅读体验。
2. 不在这里做保存名称空间范围。
3. 不提供名称空间导入导出。

验收：

1. 首屏能完成全部名称空间巡检或单名称空间巡检。
2. 未巡检时页面高度应明显短于当前版本。
3. 名称空间数量很多时页面不会被撑长。

## 给 “前端工作台与人性化 UI” agent 的任务三：日志巡检页面

参考文件：

1. `frontend/src/pages/NamespaceInspectionPage.tsx`
2. `frontend/src/pages/PodInspectionPage.tsx`
3. `frontend/src/pages/NamespaceInspectionPage.test.tsx`
4. `frontend/src/pages/PodInspectionPage.test.tsx`
5. `frontend/src/features/inspections/useRunNamespaceInspection.ts`
6. `frontend/src/features/inspections/useRunPodInspection.ts`
7. 新增的 Label Selector discovery hook

任务：

1. 页面标题改为 `日志巡检`。
2. 合并名称空间巡检和 Pod 巡检能力。
3. 顶部操作区固定为紧凑三段：
   - 名称空间下拉框
   - 范围类型：`全部 Pod` / `Label Selector` / `单个 Pod`
   - 根据范围类型展示 Label Selector 下拉框或 Pod 下拉框
4. Label Selector 必须使用自动发现候选下拉框，同时保留手动输入入口作为高级选项。
5. 保存当前范围必须改成小按钮 + 弹窗，不允许在主页面放大框。
6. 保存后的常用路径必须是紧凑列表或下拉，不允许一条路径占满整屏。
7. 事件、describe、日志摘要都必须使用可滚动代码框。
8. 日志展示默认只展示关键字命中上下 5 行；没有命中时显示短摘要，不展示全量日志。
9. Pod 列表固定高度，左侧列表 + 右侧详情；超出滚动，不撑长页面。
10. 修复“页面一直向下拉会跳到自动巡检页面”的问题。需要确认是否是滚动容器、路由链接、焦点或测试页面布局导致，修完要写明根因。

边界：

1. 不改关键字匹配算法。
2. 不改故障模板匹配逻辑。
3. 不删除 `/inspections/pod` 能力，旧路由要兼容。

验收：

1. 可选择名称空间后巡检全部 Pod 日志。
2. 可选择名称空间后用 Label Selector 巡检范围 Pod。
3. 可选择名称空间后选择单个 Pod 巡检。
4. 日志、事件、describe 不再撑高页面。
5. 保存范围、导入导出都在弹窗内完成。

## 给 “故障模板与匹配引擎” agent 的任务一：模板检查结果 UI

参考文件：

1. `frontend/src/pages/DiagnosisPage.tsx`
2. `frontend/src/features/diagnosis/DiagnosisResultPanel.tsx`
3. `frontend/src/pages/DiagnosisPage.test.tsx`
4. `frontend/src/pages/AutoInspectionPage.tsx`
5. `frontend/src/pages/AutoInspectionPage.test.tsx`

任务：

1. `模板检查` 页面最重要的信息必须是：命中了哪些模板。
2. 命中模板放在最上方，用紧凑高亮卡片或表格展示。
3. 未命中模板默认折叠，只显示模板名和未命中原因摘要。
4. 每个模板的详细证据必须点进去查看。
5. 详细证据中的日志、describe、事件、JSON 都必须使用可滚动代码框。
6. 未命中条件不要用大块 JSON 直接铺满页面。
7. 命中证据要突出：
   - 模板名
   - 命中条件数
   - 命中 Pod
   - 命中容器
   - 命中日志上下文
   - 建议动作

边界：

1. 不改后端匹配语义。
2. 不改模板创建/编辑页面。
3. 不让自动巡检页面复刻完整模板检查页面。

验收：

1. 有命中时，用户第一眼能看到命中的模板。
2. 未命中模板不会把页面拉很长。
3. 代码框可滚动，长日志不撑开页面。

## 给 “故障模板与匹配引擎” agent 的任务二：故障模板编辑 UI

参考文件：

1. `frontend/src/pages/TemplatesPage.tsx`
2. `frontend/src/pages/TemplatesPage.test.tsx`
3. `frontend/src/features/templates/useTemplates.ts`

任务：

1. 整体 UI 重新排版，降低字号和卡片高度。
2. 模板列表改为紧凑表格或左右分栏。
3. 启用状态必须用绿色，禁用灰色。
4. 新增/编辑模板建议使用弹窗或右侧抽屉，不要把全部表单一直铺在主页面。
5. 条件编辑要更像规则构建器：
   - 对象组
   - 条件类型
   - 操作符
   - 匹配值
   - 启用开关
6. 多条件列表要紧凑，可折叠，不要每条条件占大卡片。
7. 导入导出弹窗优化，JSON 使用可滚动代码框。

边界：

1. 不改模板 API。
2. 不改 matcher 行为。
3. 不引入大型 UI 依赖，除非仓库已有。

验收：

1. 模板列表 10 条以内不应导致页面过长。
2. 新增模板流程仍能完成目标、条件、建议录入。
3. 启用/禁用视觉符合绿色/灰色预期。

## 给 “关键字库与白名单” agent 的任务

参考文件：

1. `frontend/src/pages/WhitelistsPage.tsx`
2. `frontend/src/pages/WhitelistsPage.test.tsx`
3. `frontend/src/features/whitelists/useKeywords.ts`
4. `frontend/src/features/whitelists/useWhitelists.ts`

任务：

1. 页面标题改为 `关键字库`，白名单作为同页次级 tab 或分栏。
2. 关键字列表必须改为高密度表格或紧凑列表。
3. 每个关键字只展示：
   - 关键字
   - 类别
   - 严重级别
   - 启用状态
   - 是否内置
   - 操作按钮
4. 描述字段默认省略，鼠标悬停或点击详情查看完整内容。
5. 按钮改小，不要大面积占位。
6. 白名单列表同样紧凑，范围长文本默认省略，悬停展示完整范围。
7. 新增/编辑/导入/导出全部使用优化后的弹窗。
8. 导入导出的 JSON 必须使用可滚动代码框。

边界：

1. 不改关键字匹配规则。
2. 不改白名单匹配范围。
3. 不把关键字和白名单拆成两个导航入口。

验收：

1. 预置几十条关键字时页面仍短，不被每条规则撑高。
2. 能新增、编辑、启用/禁用、删除、导入、导出。
3. 前端测试覆盖弹窗打开/关闭和导入导出不占主页面。

## 给 “巡检编排与检查入口” agent 的任务

参考文件：

1. `backend/app/services/inspection_service.py`
2. `backend/app/api/routes/inspections.py`
3. `frontend/src/api/client.ts`
4. `frontend/src/api/types.ts`

任务：

1. 只在前端合并页面需要时做轻量接口支持。
2. 如果现有接口已经能支持 `全部 Pod`、`Label Selector`、`单 Pod` 三种日志巡检，不要新增接口。
3. 如必须调整请求参数，必须先让 “统一契约与数据模型” agent 更新契约。

边界：

1. 不参与页面视觉改造。
2. 不改变已有巡检语义。
3. 不把名称空间巡检导入导出重新加回来。

验收：

1. 三种日志巡检入口使用稳定。
2. 后端测试必须覆盖旧接口兼容。

## 给 “统一契约与数据模型” agent 的最终复核任务

在所有 UI 调整完成后执行。

复核重点：

1. 前端路由和 API 类型没有虚构字段。
2. Label Selector discovery 契约前后端一致。
3. `InspectionTarget`、`KeywordHit`、`TemplateMatchResult` 没有被 UI agent 私自改语义。
4. 旧路由兼容策略明确。
5. 测试断言使用新文案，不残留旧导航名。

验收：

1. 写 worklog，列出已核对文件和结论。
2. 如发现契约不一致，直接指出文件和行号，不要自行大范围重构。

## 主会话最终验收标准

所有 agent 完成后，主会话需要执行：

```bash
python3 -m pytest -q backend/tests
cd frontend && npm test -- --run
cd frontend && npm run build
```

验收通过条件：

1. 后端测试通过。
2. 前端测试通过。
3. 前端构建通过。
4. UI 主页面不再明显无限增长。
5. 日志、事件、describe、JSON 全部进入可滚动代码框。
6. 导航名符合本文件定义。
7. `日志巡检` 页面能覆盖全部 Pod、Label Selector、单 Pod 三种使用方式。

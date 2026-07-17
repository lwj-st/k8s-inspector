# Worklog: 故障模板与匹配引擎

## 时间

- 日期：2026-07-11
- Agent：Codex

## 任务范围

根据总文档 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`，本任务负责《故障模板与匹配引擎》相关能力收口，并补齐前端已落地的模板检查闭环。

本任务只负责：

1. 故障模板的数据消费与展示闭环
2. 模板检查结果里的命中条件、未命中条件输出
3. 模板检查入口与前端交互整理
4. 与关键字库/白名单、巡检结果之间的边界对齐

本任务不负责：

1. Kubernetes 采集逻辑
2. saved targets 的完整产品闭环
3. 白名单、关键字管理页的主能力设计
4. 模板录入/编辑/导入/导出后台接口的新增实现

## 本次已完成内容

### 1. 模板检查页改成真实执行入口

已调整 `frontend/src/pages/DiagnosisPage.tsx`：

- 去掉手填名称空间、scope 的旧交互
- 改成“按已录入模板直接检查”的单入口
- 点击后直接调用：
  - `POST /api/v1/diagnoses/run`
- 前端不再要求用户重复输入模板里已经绑定的巡检范围

这符合总文档里“模板里已指定名称空间及 label，只需要对指定范围巡检”的要求。

### 2. 模板检查结果支持条件级展示

诊断结果页已支持展示：

- 命中的模板
- 模板原因
- 模板建议
- 命中条件数量
- 命中条件明细
- 未命中条件明细

前端已消费：

- `matched_conditions`
- `unmatched_conditions`

并将条件翻译为可读文案，例如：

- 对象组 `api` 的 Pod 状态等于 `CrashLoopBackOff`
- 对象组 `api` 在日志中包含 `connection refused`

### 3. 模板页展示已对齐对象组概念

已调整 `frontend/src/pages/TemplatesPage.tsx`：

- 优先展示 `target_groups`
- 兼容 `targets`
- 每个模板按“对象组”展示绑定范围
- 条件按自然语言方式展示
- 展示整体条件关系 `joint_rule.operator`

这让模板结构更接近产品语义：

1. 先定义对象组
2. 再定义条件
3. 最后给出原因和建议

### 4. 模板检查接口前端契约已收口

已调整：

- `frontend/src/api/client.ts`
- `frontend/src/features/diagnosis/useRunDiagnosis.ts`
- `frontend/src/api/types.ts`

当前前端按统一 payload 调用模板检查：

```ts
runDiagnosis({
  namespace?: string | null,
  scope?: string | null,
  template_ids?: number[],
})
```

同时诊断结果类型已补齐：

- `matched_conditions`
- `unmatched_conditions`
- `namespace?: string | null`

### 5. 命名空间巡检页的“忽略此报错”已与模板链路对齐

虽然这部分跨到白名单联动，但本次为了保证模板匹配输入一致，已补齐：

- `frontend/src/pages/NamespaceInspectionPage.tsx`

现在“忽略此报错”会真实调用：

- `POST /api/v1/whitelists/ignore`

而不是仅在当前页面临时隐藏。

这对模板引擎有直接意义：

1. 巡检结果中的噪音命中可真正入白名单
2. 后续模板检查可复用同一份过滤后的输入
3. 避免模板再次命中本应忽略的日志

## 主要涉及文件

### 前端

- `frontend/src/pages/DiagnosisPage.tsx`
- `frontend/src/pages/DiagnosisPage.test.tsx`
- `frontend/src/pages/TemplatesPage.tsx`
- `frontend/src/pages/TemplatesPage.test.tsx`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/features/diagnosis/useRunDiagnosis.ts`

### 参考文档

- `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`
- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `worklog/codex-contract-models-2026-07-11.md`
- `worklog/codex-keyword-whitelist-2026-07-11.md`

## 验证结果

已执行前端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `7 passed`
- `11 tests passed`

已执行后端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest -q backend/tests
```

结果：

- `32 passed, 1 warning`

## 当前边界结论

### 1. 模板页当前已能“看”和“查”，但还不能“录”

当前已完成：

- 模板展示
- 模板检查
- 模板结果解释

当前仍未完成：

- 模板录入 UI
- 模板编辑 UI
- 模板启停 UI
- 模板导入导出 UI

这部分应继续由后续《故障模板与匹配引擎》或专门的模板录入任务完成。

### 2. 模板检查前端不再自己拼业务逻辑

前端当前只负责：

- 发起模板检查
- 展示后端返回结果

前端不负责：

- 自己计算模板是否命中
- 自己扫描日志关键字
- 自己执行白名单规则

这和总文档里“不要在前端自行补后端缺失逻辑”的要求一致。

### 3. 模板日志条件应继续统一消费 `log_hits`

从契约与协作文档看，这条规则必须继续保持：

1. 模板的 `log_keyword` 不应再直接扫 `log_summary`
2. 应统一消费巡检产出的 `log_hits`
3. `whitelisted=true` 的命中不应再作为模板异常输入

当前本次前端收口是按这个方向落地的，但后续 agent 仍需继续确认后端匹配实现没有回退。

## 需要和其他 agent 协商/同步的事项

### 1. 与《统一契约与数据模型》协同

需要继续遵守：

- 新代码主用 `targets`
- `target_groups` 仅作兼容展示或兼容输入
- `condition_type`、`operator` 使用冻结枚举

后续 agent 不要再扩一套新的模板条件字段。

## 追加记录：2026-07-17 slice 6 手动模板匹配入口

### 1. 本轮目标

根据 `docs/superpowers/plans/2026-07-17-auto-inspection-slice-5-acceptance-and-slice-6-instructions.md`，本轮只补前端手动模板匹配入口与结果展示，不改后端 matcher 语义，不把诊断结果塞回模板录入页。

本轮只做：

1. 在名称空间巡检页增加“模板匹配”入口
2. 复用诊断接口结果，展示命中模板与未命中模板
3. 展示每个模板的命中条件、未命中条件、证据摘要、执行状态
4. 补齐前端测试与构建验证

本轮不做：

1. 完整日志原文
2. 完整 describe 原文
3. AI 补充诊断交互
4. 自动定时诊断
5. 模板录入器能力扩展

### 2. 已落地实现

新增可复用结果面板：

- `frontend/src/features/diagnosis/DiagnosisResultPanel.tsx`

职责：

1. 统一承接 `DiagnosisResponse`
2. 处理 4 种前端状态：
   - idle
   - loading
   - error
   - result
3. 统一展示：
   - 命中模板
   - 未命中模板
   - 命中条件
   - 未命中条件
   - 模板级证据摘要
   - 全局证据摘要

这样 `DiagnosisPage` 和 `NamespaceInspectionPage` 不再各自拼一套模板结果 UI。

### 3. 名称空间巡检页新增模板匹配入口

已调整：

- `frontend/src/pages/NamespaceInspectionPage.tsx`

行为：

1. 只有完成一次名称空间巡检后，页面中部才会出现“模板匹配”区域
2. 点击“模板匹配”后调用：
   - `POST /api/v1/diagnoses/run`
3. 请求参数来自当前巡检范围：
   - `namespace = 当前巡检 namespace`
   - `scope = 当前巡检 label_selector`
4. 结果以内联紧凑面板方式展示，不跳新页，不展开完整日志

这样用户在看名称空间异常 Pod 时，可以直接继续判断“这是不是某个已录入故障模板”。

### 4. 独立模板检查页已同步复用结果面板

已调整：

- `frontend/src/pages/DiagnosisPage.tsx`

当前页面仍然保留“按已录入模板直接检查”的单按钮入口，但结果展示改成复用统一面板，避免：

1. 命名空间巡检页和模板检查页展示不一致
2. 只展示命中模板、不展示未命中模板
3. loading / error / empty 状态表现分裂

### 5. 测试覆盖

已补测试：

- `frontend/src/pages/DiagnosisPage.test.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`

新增覆盖点：

1. 模板检查页：
   - 命中模板
   - 未命中模板
   - loading
   - failure
   - empty
2. 名称空间巡检页：
   - 手动触发模板匹配
   - 请求参数带当前 namespace / label scope
   - 内联展示命中模板与未命中模板

### 6. 本轮边界结论

本轮仍保持边界清晰：

1. 模板录入器只负责录入模板，不展示诊断运行结果
2. 巡检页只负责触发并查看当前范围诊断结果，不修改模板定义
3. 诊断结果面板只负责解释后端返回，不自己做模板命中判断
4. 模板匹配结果只展示摘要证据，不展示完整日志和完整 describe

后续 agent 如果继续做这块，应继续遵守：

1. 不要把模板录入页改成“录入 + 运行 + 结果”三合一大页
2. 不要让前端自己推断模板是否命中
3. 不要重新引入手工填写模板检查 namespace 的旧交互

### 7. 本轮验收命令

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `8 files passed`
- `41 tests passed`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- 前端生产构建通过

### 8. 协作提醒

当前工作区里还有其他 agent 的未提交改动，例如：

- `backend/`
- `docs/superpowers/plans/`
- `frontend/src/api/`
- `frontend/src/styles.css`

本轮未回退这些改动，也未尝试整理它们。后续合并时应按功能边界分别审阅，不要把本轮“模板匹配入口”与其他切片混在一起判断。

### 2. 与《关键字库与白名单》协同

需要继续保持：

- 模板日志条件消费 `log_hits`
- 白名单忽略结果应影响模板匹配
- “忽略此报错”必须是持久化白名单，不是页面临时状态

### 3. 与《巡检编排与检查入口》协同

当前模板页已经假设：

- 模板自带范围
- 检查入口可直接执行模板检查

如果后续入口字段调整，需要优先同步 `docs/superpowers/plans/2026-07-11-api-contract.md`，不要让前端私自猜接口。

### 4. 与《前端工作台与人性化 UI》协同

当前模板检查页已从“手工输范围”改成“直接执行模板检查”，后续 UI agent 需要继续优化：

1. 模板检查空状态
2. 多模板命中时的排序与分组
3. 模板详情抽屉/侧栏
4. 模板录入器的人性化条件编辑体验

但不要把本次已经去掉的“手工填写模板范围”交互再加回来。

## 当前问题记录

### 1. 总文档中的“完成度”描述与仓库当前状态已有偏差

总文档中写到《故障模板与匹配引擎》完成度约 `55%`，但按 2026-07-11 当前仓库状态看：

- 模板检查前端闭环已可用
- 结果级解释已可用
- 白名单联动已接通

因此后续评估时应区分：

1. “模板检查闭环”已基本可用
2. “模板录入/编辑/导入导出”仍明显未完成

### 2. 诊断页旧交互曾与当前需求冲突

本次修正前，诊断页仍残留旧模式：

- 依赖手工 scope
- 有旧模板卡片流程

现已改正。后续 agent 不要再按旧交互继续开发。

### 3. 模板后端管理能力仍待补齐

当前从总文档和现状判断，后端仍可能缺少以下正式能力：

1. 模板新增
2. 模板编辑
3. 模板启停
4. 模板导入导出

这不是本次前端收口能替代的，需要独立继续开发。

## 当前结论

《故障模板与匹配引擎》本轮已完成到可交接状态，已落地的部分包括：

1. 模板检查页真实可用
2. 模板结果支持条件级解释
3. 模板展示页已按对象组语义整理
4. 白名单忽略动作已与模板输入链路对齐

后续最适合继续拆给其他 agent 的子任务是：

1. 模板录入/编辑/启停/导入导出后端接口
2. 模板录入器前端 UI
3. 模板匹配规则语义进一步收口与后端测试补强

## 追加记录：本轮继续开发

### 1. 已补齐 matcher operator 语义

本轮已继续收口 `backend/app/engine/matcher.py`：

- `pod_status`
  - 支持 `equals`
  - 支持 `in`
- `log_keyword`
  - 支持 `contains`
  - 匹配时同时兼顾 `keyword` 和 `matched_text`
- `event_keyword`
  - 支持 `contains`
- `restart_count`
  - 支持 `gte`
  - 支持 `lte`
- `related_object_status`
  - 支持 `equals`
  - 支持 `in`

这样模板条件不再只靠硬编码判断，和契约里的 operator 基本对齐。

### 2. 已收紧诊断响应 schema

本轮已调整 `backend/app/schemas/diagnosis.py`：

- `DiagnosisConditionResult.type`
  - 改为复用 `TemplateConditionType`
- `DiagnosisConditionResult.operator`
  - 改为复用 `TemplateConditionOperator`
- `DiagnosisResponse.status`
  - 收紧为：
    - `matched`
    - `unmatched`
    - `llm_supplemented`
- `DiagnosisResponse.direction`
  - 当前收紧为 `template_check`

这解决了总文档里提到的“诊断响应字段仍是宽松字符串”的问题。

### 3. 已补模板启停/导入/导出接口

本轮已补齐模板管理接口：

- `POST /api/v1/templates/{template_id}/enable`
- `POST /api/v1/templates/{template_id}/disable`
- `GET /api/v1/templates/export`
- `POST /api/v1/templates/import`

同时补了对应 service：

- `set_template_enabled`
- `export_templates`
- `import_templates`

### 4. 本轮顺手修复的兼容问题

在补模板接口测试时，发现：

- `FaultTemplateRead` 在 `joint_rule=None` 时会触发兼容逻辑报错

已修复：

- `backend/app/schemas/template.py`

这个问题虽然不是本轮主目标，但会直接影响模板接口稳定性，因此一并处理。

### 5. 本轮验证结果

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest -q backend/tests
```

结果：

- `47 passed, 1 warning`

### 6. 当前新的边界结论

1. 模板匹配 operator 语义已明显比之前完整
2. 诊断响应 schema 已不再放任 `type/operator/status` 漫游
3. 模板后端管理能力里，启停/导入/导出已补齐
4. 但模板录入/编辑 UI 仍未完成
5. 模板匹配对更复杂布尔表达式的支持仍只停留在 `joint_rule.operator` 级别

## 追加记录：2026-07-12 模板录入器 UI

### 1. 本轮目标

在后端模板接口已经稳定的前提下，完成前端模板录入器，补齐：

1. 创建
2. 编辑
3. 删除
4. 启用
5. 停用
6. 导入
7. 导出

并保证录入器是可视化条件块，不让用户把 JSON 作为唯一录入入口。

### 2. 本轮已完成内容

#### 2.1 模板 API 封装已补齐

已补：

- `createTemplate`
- `updateTemplate`
- `deleteTemplate`
- `enableTemplate`
- `disableTemplate`
- `exportTemplates`
- `importTemplates`

文件：

- `frontend/src/api/client.ts`

#### 2.2 模板 hook 已从只读改成可写

已重写：

- `frontend/src/features/templates/useTemplates.ts`

当前支持：

- 刷新
- 新增
- 编辑
- 删除
- 启停
- 导入
- 导出

#### 2.3 模板页已变成真正的模板录入器

已重写：

- `frontend/src/pages/TemplatesPage.tsx`

当前页面支持：

1. 多对象组录入
   - `target_ref`
   - `namespace`
   - `label_selector`
   - `pod_name_pattern`
   - `resource_scope`

2. 多条件块录入
   - `log_keyword`
   - `pod_status`
   - `restart_count`
   - `event_keyword`
   - `related_object_status`

3. 条件 operator 严格复用后端契约
   - `equals`
   - `in`
   - `contains`
   - `gte`
   - `lte`

4. `joint_rule`
   - `AND`
   - `OR`

5. 诊断描述信息
   - `reason`
   - `suggestion`
   - `command`
   - `risk_note`

6. 模板列表操作
   - 编辑
   - 停用/启用
   - 删除

7. 模板迁移能力
   - JSON 导出
   - JSON 导入

#### 2.4 条件块已提供自然语言预览

每个条件块都会实时显示自然语言预览，例如：

- 对象组 `group-1` 在日志中包含 `timeout`
- 对象组 `api` 的 Pod 状态等于 `CrashLoopBackOff`
- 对象组 `worker` 的重启次数 `gte 3`

这符合总文档里“模板录入必须可视化”的要求。

#### 2.5 本轮顺手修复的交互细节

1. 对象组改名后，引用它的条件块 `target_ref` 会自动跟着更新
2. 新增对象组时不再自动追加一条无意义条件
3. `select` / `textarea` 已纳入现有表单样式

### 3. 本轮主要文件

- `frontend/src/api/client.ts`
- `frontend/src/features/templates/useTemplates.ts`
- `frontend/src/pages/TemplatesPage.tsx`
- `frontend/src/pages/TemplatesPage.test.tsx`
- `frontend/src/styles.css`

### 4. 本轮验证结果

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `7 passed`
- `14 tests passed`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- build 成功

### 5. 当前结论

模板录入器 UI 本轮已完成到可交接状态：

1. 不再只是模板展示页
2. 已具备真实录入和管理能力
3. 条件块、对象组、AND/OR、建议信息都能在界面中配置
4. 导入导出已可用于跨环境迁移

### 6. 后续可继续交给其他 agent 的点

1. 模板页字段文案进一步运维化
2. 模板列表增加搜索/筛选
3. 导入 JSON 的格式错误提示做得更友好
4. 将 `resource_scope` 从多选复选框进一步收口成更明确的产品语义

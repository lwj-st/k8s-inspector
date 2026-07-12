# K8s Inspector 后续任务开发指令

## 1. 当前状态结论

本文档基于 2026-07-11 仓库现状整理，用于指挥后续多个开发会话分工开发。

当前整体结论：

- 6 个任务都已经有不同程度的实现，不是空白项目
- 后端基础能力已经较多，测试当前通过
- 前端已有工作台和页面雏形，但距离“人性化可用”还有明显差距
- 后续不能让各任务各自扩字段、各自拼逻辑，必须先收口契约

当前验证结果：

- 后端：`cd backend && python3 -m pytest -q`，结果 `32 passed, 1 warning`
- 前端：`cd frontend && npm test -- --run`，结果 `7 files / 11 tests passed`

注意：

- 当前工作区存在未提交改动和未跟踪文件
- 不要删除或回滚其他开发会话的改动
- 不要把 `k8s_inspector.db`、`root-test.db`、`subpath-test.db` 这类本地数据库文件纳入业务提交

## 2. 六个任务完成情况

### 2.1 统一契约与数据模型

完成度：约 70%。

已完成：

- 已有统一模型：
  - `InspectionTarget`
  - `EvidenceBundle`
  - `KeywordHit`
  - `TemplateTarget`
  - `TemplateCondition`
  - `TemplateMatchResult`
- 前端 `frontend/src/api/types.ts` 已有对应类型
- 后端测试 `test_contract_models.py` 已覆盖核心契约
- 已新增保存巡检对象模型 `SavedInspectionTarget`

主要缺口：

- 还没有单独 API 契约文档
- 字段命名仍存在新旧兼容混用，例如 `targets` / `target_groups`
- `condition_type`、`operator` 仍是宽松字符串，没有形成稳定枚举
- 前后端类型一致性依赖人工维护，缺少明确禁止扩散规则

结论：

- 该任务必须先收口，作为后续并行开发的前置任务

### 2.2 巡检编排与检查入口

完成度：约 70%。

已完成：

- 已有名称空间巡检接口
- 已有单 Pod 巡检接口
- 已有统一巡检入口 `POST /api/v1/inspections/run`
- 已支持巡检历史记录
- 已有保存巡检对象基础接口

主要缺口：

- 前端单 Pod 巡检页没有调用专用 `POST /api/v1/inspections/pod/run`，而是先跑名称空间巡检再在前端找 Pod
- 保存巡检对象只有新增、列表、删除，缺少更新、导入、导出
- 编排层和采集层都在组装 `inspection_target` / `evidence_bundle`，职责有重复

结论：

- 后端入口基本可用，但要做一次编排职责收口

### 2.3 K8s 采集与证据抽取

完成度：约 75%。

已完成：

- Kubernetes provider 已支持：
  - Pod
  - Service
  - Ingress
  - DaemonSet
  - Secret
  - Event
  - 当前日志
  - 前一次日志
- Pod 证据已包含：
  - `node_name`
  - `containers`
  - `describe_summary`
  - `log_summary`
  - `previous_log_summary`
  - `related_resources`
- 已有 `test_kubernetes_provider.py` 覆盖部分采集行为

主要缺口：

- `describe_summary` 仍是手工摘要，不是真正等价于 `kubectl describe` 的完整关键信息
- Pod 巡检当前通过名称空间巡检后筛选 Pod，真实集群大名称空间下效率不理想
- 资源使用仍是 `n/a`，未接 Metrics API
- provider 里有 `_log_hits_from_pod`，inspection service 里也会重新做关键字命中，职责重复

结论：

- 采集能力可用，但需要聚焦“证据质量”和“职责单一”

### 2.4 关键字库与白名单

完成度：约 75%。

已完成：

- 已有关键字库模型、服务和 API
- 已有内置关键字初始化
- 已有白名单模型、服务和 API
- 白名单支持：
  - `namespace`
  - `label_selector`
  - `pod_name_pattern`
  - `container_name`
  - `keyword`
- 名称空间巡检页“忽略此报错”已接真实接口
- 关键字和白名单导入导出后端接口已存在

主要缺口：

- 白名单匹配里的 `pod_name_pattern` 当前只是字符串包含，不是明确的通配符或正则语义
- Pod 巡检页里的“忽略此报错”只是前端本地状态，没有落白名单接口
- 白名单/关键字前端缺少编辑、删除、启停、导入、导出
- 模板匹配没有统一消费 `log_hits` 和白名单过滤结果，仍可能绕过关键字库与白名单

结论：

- 基础能力可用，但必须补齐与模板引擎的边界

### 2.5 故障模板与匹配引擎

完成度：约 55%。

已完成：

- 模板支持对象组 `namespace + label selector`
- 模板支持多条件
- 匹配引擎支持：
  - `pod_status`
  - `log_keyword`
  - `event_keyword`
  - `restart_count`
  - `related_object_status`
- 诊断执行时可以按模板预设范围检查
- 诊断结果已返回命中条件和未命中条件

主要缺口：

- 模板页面只有展示，没有真正的录入、编辑、启停、导入、导出 UI
- 模板后端缺少启停、导入、导出接口
- `log_keyword` 当前直接扫 `log_summary`，没有统一使用 `KeywordHit`
- 白名单过滤结果没有作为模板匹配的统一输入
- `operator` 支持不完整，例如 `equals`、`in`、`contains`、`gte` 的语义没有统一实现
- `join_operator` 和 `joint_rule` 的关系还不够清晰

结论：

- 模板引擎是下一阶段重点，不能只做页面，必须先把匹配语义收口

### 2.6 前端工作台与人性化 UI

完成度：约 55%。

已完成：

- 首页已改成排障工作台
- 有名称空间巡检页
- 有单 Pod 巡检页
- 有模板检查页
- 有模板展示页
- 有关键字库与白名单页面
- 前端测试当前通过

主要缺口：

- 页面仍有 `demo` 默认值和内置 demo 快捷对象，不适合真实使用
- 单 Pod 巡检页没有调用专用 Pod 巡检接口
- 模板录入页不是条件块编辑器，只是列表展示
- 白名单页缺少编辑、删除、启停、导入、导出
- 首页“最近使用的巡检对象”尚未真正展示保存对象
- UI 还有较多说明型文案，后续要转成实际控件和状态

结论：

- UI 已有方向，但还不是最终可用体验

## 3. 总体开发顺序

后续开发按 4 个阶段推进。

### 阶段 0：收口前置状态

执行人：总控/验收负责人。

目标：

- 确认当前未提交改动归属
- 不清理、不回滚其他开发会话的成果
- 将本文档作为后续分工依据

完成标准：

- 所有任务开工前阅读本文档
- 所有任务明确自己的文件边界

### 阶段 1：串行任务，先冻结契约

执行人：统一契约与数据模型。

原因：

- 这是所有后续任务的共同前提
- 如果不先冻结，模板、白名单、前端类型会继续发散

完成后，巡检编排与检查入口、K8s 采集与证据抽取、关键字库与白名单、故障模板与匹配引擎可以并行。

### 阶段 2：后端并行开发

可并行执行：

- 巡检编排与检查入口
- K8s 采集与证据抽取
- 关键字库与白名单
- 故障模板与匹配引擎

并行限制：

- 不允许私自修改 `backend/app/schemas/common.py`
- 需要改契约时，先回到“统一契约与数据模型”的契约文档和 schema
- 不允许在前端自行补后端缺失逻辑

### 阶段 3：前端集中收口

执行人：前端工作台与人性化 UI。

原因：

- 前端依赖接口稳定
- UI 要基于真实接口做交互闭环

前端工作台与人性化 UI 可以提前做视觉和布局，但正式联调必须等“统一契约与数据模型”和“巡检编排与检查入口”完成。

### 阶段 4：整体验收与回归

执行人：总控/验收负责人或“整体质量验收”。

目标：

- 跑完整测试
- 检查工作流
- 清理本地数据库和构建产物
- 输出最终交接说明

## 4. 给“统一契约与数据模型”的开发指令

### 4.1 任务目标

冻结后端 schema、前端类型和 API 契约，禁止后续任务各自扩字段。

### 4.2 主要文件

允许重点修改：

- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/whitelist.py`
- `backend/app/schemas/keyword.py`
- `backend/app/schemas/saved_target.py`
- `frontend/src/api/types.ts`
- `docs/superpowers/plans/2026-07-11-api-contract.md`

谨慎修改：

- `backend/app/models/`
- `backend/tests/test_contract_models.py`

### 4.3 必做事项

1. 新建或更新 API 契约文档：
   - 建议文件：`docs/superpowers/plans/2026-07-11-api-contract.md`
2. 明确枚举值：
   - `InspectionTarget.type`
   - `TemplateCondition.condition_type`
   - `TemplateCondition.operator`
   - `TemplateCondition.join_operator`
   - `KeywordHit.severity`
3. 明确 `targets` 和 `target_groups` 的最终策略：
   - 推荐：API 主用 `targets`
   - `target_groups` 只作为兼容输入或兼容输出，不再让新代码依赖
4. 明确 `KeywordHit` 是模板日志条件的统一输入
5. 明确 `EvidenceBundle` 由哪个模块生成，避免 provider 和 service 双方重复拼装
6. 补测试：
   - schema 校验
   - 旧字段兼容
   - 前后端类型字段对齐说明

### 4.4 禁止事项

- 不做 UI 页面
- 不写 Kubernetes 采集逻辑
- 不实现模板匹配业务逻辑

### 4.5 验收标准

- `python3 -m pytest -q` 通过
- 契约文档能让其他任务明确字段含义
- `frontend/src/api/types.ts` 与后端 schema 字段一致

## 5. 给“巡检编排与检查入口”的开发指令

### 5.1 任务目标

把名称空间巡检、单 Pod 巡检、统一巡检入口和保存巡检对象整理成清晰的运行编排层。

### 5.2 主要文件

允许重点修改：

- `backend/app/services/inspection_service.py`
- `backend/app/api/routes/inspections.py`
- `backend/app/services/saved_target_service.py`
- `backend/app/api/routes/saved_targets.py`
- `backend/tests/test_inspection_api.py`
- `backend/tests/test_saved_targets_api.py`

谨慎修改：

- `backend/app/schemas/inspection.py`
- `backend/app/schemas/saved_target.py`

### 5.3 必做事项

1. 让单 Pod 巡检服务直接调用 provider 的 Pod 能力，不依赖前端跑名称空间巡检后筛选
2. 明确 `inspection_service` 是 `EvidenceBundle` 最终组装者，或按“统一契约与数据模型”的契约调整
3. 补齐保存巡检对象能力：
   - 列表
   - 新增
   - 更新
   - 删除
   - 导入
   - 导出
4. 统一保存对象的运行入口：
   - 保存对象为 namespace 时，运行名称空间巡检
   - 保存对象为 pod 时，运行 Pod 巡检
5. 错误处理：
   - 找不到 Pod 返回 404
   - namespace 为空返回 422
   - 保存对象不存在返回 404

### 5.4 禁止事项

- 不实现关键字匹配细节
- 不实现模板匹配逻辑
- 不写前端页面

### 5.5 验收标准

- `python3 -m pytest -q` 通过
- 保存对象导入导出有测试
- Pod 巡检接口返回专用 `PodInspectionResponse`

## 6. 给“K8s 采集与证据抽取”的开发指令

### 6.1 任务目标

提升真实 Kubernetes 采集质量，保持只读，输出稳定证据。

### 6.2 主要文件

允许重点修改：

- `backend/app/providers/base.py`
- `backend/app/providers/kubernetes_provider.py`
- `backend/app/providers/mock_provider.py`
- `backend/tests/test_kubernetes_provider.py`

谨慎修改：

- `backend/app/schemas/inspection.py`
- `backend/app/schemas/common.py`

### 6.3 必做事项

1. 优化 `run_pod_inspection`：
   - 使用 `read_namespaced_pod`
   - 不通过全名称空间列表再筛选
2. 提升 `describe_summary` 质量：
   - phase
   - node
   - container waiting/terminated reason
   - restart count
   - image
   - recent warning events
3. 当前日志和前一次日志都要按容器维度处理
4. 资源使用如果 Metrics API 不可用，必须明确返回 `n/a` 和原因，不要静默误导
5. 移除 provider 内部伪造的 `_log_hits_from_pod` 或按“统一契约与数据模型”的契约调整
6. 保持只读权限，不增加任何写操作

### 6.4 禁止事项

- 不做白名单过滤
- 不做模板匹配
- 不改 UI

### 6.5 验收标准

- `python3 -m pytest -q` 通过
- mock provider 和 kubernetes provider 输出结构一致
- 大名称空间下单 Pod 巡检不会全量扫描所有 Pod

## 7. 给“关键字库与白名单”的开发指令

### 7.1 任务目标

完善关键字库、白名单和日志命中能力，并保证模板引擎复用同一套结果。

### 7.2 主要文件

允许重点修改：

- `backend/app/services/keyword_service.py`
- `backend/app/services/whitelist_service.py`
- `backend/app/api/routes/keywords.py`
- `backend/app/api/routes/whitelists.py`
- `backend/app/models/keyword_rule.py`
- `backend/app/models/whitelist.py`
- `backend/tests/test_whitelist_api.py`

谨慎修改：

- `backend/app/services/inspection_service.py`
- `backend/app/schemas/common.py`

### 7.3 必做事项

1. 明确 `pod_name_pattern` 语义：
   - 推荐支持 shell 风格通配符，例如 `demo-api-*`
   - 使用标准库实现，不要手写复杂匹配
2. 补齐启停接口：
   - 关键字启停
   - 白名单启停
3. 确认导入导出格式稳定
4. 让 `match_log_text` 返回的 `KeywordHit` 成为模板日志条件的输入
5. 补测试：
   - label selector 白名单
   - pod name pattern 白名单
   - container 白名单
   - whitelisted hit 不参与模板命中

### 7.4 禁止事项

- 不实现模板条件组合逻辑
- 不采集 Kubernetes 日志
- 不写模板编辑器 UI

### 7.5 验收标准

- `python3 -m pytest -q` 通过
- `忽略此报错` 创建的白名单能在下一次巡检中生效
- 被白名单命中的日志不会被模板当作有效异常

## 8. 给“故障模板与匹配引擎”的开发指令

### 8.1 任务目标

把模板匹配从“能跑”提升到“语义稳定、可解释、可扩展”。

### 8.2 主要文件

允许重点修改：

- `backend/app/engine/matcher.py`
- `backend/app/services/template_service.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/api/routes/templates.py`
- `backend/app/api/routes/diagnoses.py`
- `backend/tests/test_matcher.py`
- `backend/tests/test_template_api.py`
- `backend/tests/test_diagnosis_api.py`

谨慎修改：

- `backend/app/schemas/template.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/common.py`

### 8.3 必做事项

1. 统一 operator 语义：
   - `equals`
   - `in`
   - `contains`
   - `gte`
   - `lte`
2. `log_keyword` 不再直接扫原始 `log_summary`
   - 必须消费 `KeywordHit`
   - 默认只使用 `whitelisted=false` 的命中
3. 对象组匹配多个 Pod 时，保持当前规则：
   - 任一 Pod 命中，该条件成立
4. 明确条件组合：
   - 模板级 `joint_rule.operator` 控制整体 AND/OR
   - 条件级 `join_operator` 仅用于 UI 展示或后续扩展，当前不要产生两套逻辑
5. 补齐模板接口：
   - 启用
   - 停用
   - 导入
   - 导出
6. 模板检查结果必须输出：
   - 命中模板
   - 未命中模板
   - 命中条件
   - 未命中条件
   - 证据引用

### 8.4 禁止事项

- 不采集 Kubernetes 数据
- 不写关键字匹配扫描器
- 不做前端模板编辑器

### 8.5 验收标准

- `python3 -m pytest -q` 通过
- 每种 condition type 至少有一个 matcher 单测
- 白名单命中不会导致模板误命中

## 9. 给“前端工作台与人性化 UI”的开发指令

### 9.1 任务目标

把当前页面从“可展示”推进到“实际排障时少输入、少跳转、结果清楚”。

### 9.2 主要文件

允许重点修改：

- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/DiagnosisPage.tsx`
- `frontend/src/pages/TemplatesPage.tsx`
- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/features/`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- 对应前端测试文件

谨慎修改：

- 后端文件

### 9.3 必做事项

1. 去掉硬编码 demo 快捷对象
   - 首页和巡检页改用真实保存对象
2. 单 Pod 巡检页调用 `POST /api/v1/inspections/pod/run`
   - 不再跑名称空间巡检后前端筛选
3. 命名空间巡检页继续保持异常优先
   - 正常对象折叠
   - 日志命中明确区分已白名单和未白名单
4. Pod 巡检页的“忽略此报错”必须调用真实白名单接口
5. 模板页实现条件块编辑器
   - 对象组编辑
   - 条件类型选择
   - operator 选择
   - expected value 输入
   - 自然语言预览
6. 诊断页展示未命中模板和未命中条件
7. 白名单页补齐：
   - 编辑
   - 删除
   - 启停
   - 导入
   - 导出
8. 控件要面向运维重复使用：
   - 少说明文案
   - 多直接操作
   - 状态明确
   - 不做营销式页面

### 9.4 禁止事项

- 不在前端实现模板匹配逻辑
- 不在前端自行判断白名单是否命中
- 不绕过后端 API

### 9.5 验收标准

- `npm test -- --run` 通过
- 页面没有硬编码 demo 作为主要入口
- 关键工作流可完成：
  - 保存对象后一键巡检
  - 单 Pod 巡检
  - 忽略日志命中
  - 创建模板
  - 运行模板检查

## 10. 给“整体质量验收”的开发指令

### 10.1 任务目标

在各任务完成后做统一质量检查，避免模块各自通过但整体不可用。

### 10.2 必查事项

1. 后端测试：
   - `cd backend && python3 -m pytest -q`
2. 前端测试：
   - `cd frontend && npm test -- --run`
3. 前端构建：
   - `cd frontend && npm run build`
4. API 契约：
   - 后端 schema 与前端 type 字段一致
5. 工作流：
   - 名称空间巡检
   - 单 Pod 巡检
   - 忽略此报错
   - 模板录入
   - 模板检查
6. Git 状态：
   - 不提交本地数据库文件
   - 不提交无关构建缓存

### 10.3 验收输出

整体质量验收需要输出：

- 通过项
- 失败项
- 需要返工的任务
- 具体文件和原因

## 11. 并行安排建议

推荐调度方式：

1. 先派“统一契约与数据模型”
2. “统一契约与数据模型”完成并通过测试后，同时派“巡检编排与检查入口”、“K8s 采集与证据抽取”、“关键字库与白名单”、“故障模板与匹配引擎”
3. “前端工作台与人性化 UI”可以提前看文档和现有页面，但正式联调等“统一契约与数据模型”、“巡检编排与检查入口”、“关键字库与白名单”、“故障模板与匹配引擎”的接口稳定
4. 最后派“整体质量验收”做总体验收

不推荐：

- “前端工作台与人性化 UI”先大改 UI，然后再等后端补接口
- “故障模板与匹配引擎”自己扩 `TemplateCondition`
- “关键字库与白名单”自己决定白名单对模板是否生效
- “K8s 采集与证据抽取”在 provider 里继续生成伪 `log_hits`

## 12. 分支与合代码要求

每个任务建议使用独立分支：

- `codex/contract-models`
- `codex/inspection-orchestration`
- `codex/k8s-evidence`
- `codex/keyword-whitelist`
- `codex/template-engine`
- `codex/operator-ui`
- `codex/qa-integration`

合代码要求：

- 优先 rebase，不使用 merge commit
- 每个任务合入前必须跑本任务相关测试
- 涉及共享契约的改动必须先同步“统一契约与数据模型”的契约文档
- 不允许为了测试通过删除其他模块测试

## 13. 当前最高优先级

“统一契约与数据模型”已完成首轮开发并通过 review，可作为后续任务的共同基线。

后续最高优先级调整为：

- “关键字库与白名单”
- “故障模板与匹配引擎”
- “巡检编排与检查入口”

原因：

- 契约已经冻结，但关键字 severity 和诊断条件返回仍有需要收口的风险点
- 模板引擎必须尽快改为消费 `KeywordHit`
- 巡检编排需要配合契约明确 `EvidenceBundle` 的最终组装边界

“K8s 采集与证据抽取”可以并行，但要严格限制在 provider 层，不要改关键字和模板逻辑。

“前端工作台与人性化 UI”等接口稳定后集中做体验收口。

## 14. “统一契约与数据模型”Review 结论与继续派发

Review 时间：2026-07-11。

已检查：

- `worklog/codex-contract-models-2026-07-11.md`
- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/schemas/common.py`
- `backend/app/schemas/saved_target.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/diagnosis.py`
- `frontend/src/api/types.ts`
- `backend/tests/test_contract_models.py`

验证结果：

- 后端：`python3 -m pytest -q backend/tests` 通过，`35 passed, 1 warning`
- 前端：`npm test -- --run` 通过，`7 files / 11 tests passed`
- 前端构建：`npm run build` 通过

### 14.1 Review 结论

“统一契约与数据模型”可以放行。

已完成的有效成果：

- 新增 API 契约冻结文档
- 后端共享 schema 增加枚举约束
- 前端类型同步为联合类型
- `targets` 作为新主字段，`target_groups` 作为兼容字段
- 明确 `KeywordHit` 是模板日志条件输入
- 明确 `EvidenceBundle` 由 `inspection_service` 最终组装
- 契约测试已覆盖旧字段兼容和非法枚举拒绝

### 14.2 Review 发现的问题

问题 1：关键字规则 severity 仍是任意字符串。

位置：

- `backend/app/schemas/keyword.py`
- `frontend/src/api/types.ts`

影响：

- `KeywordHit.severity` 已冻结为 `info | warning | error | critical`
- 但 `KeywordRule.severity` 仍允许任意字符串
- 如果用户录入非法 severity，后续日志命中生成 `KeywordHit` 时可能触发响应校验失败

处理要求：

- 交给“关键字库与白名单”优先处理
- `KeywordRule.severity` 必须复用同一套 severity 枚举
- 前端 `KeywordRule.severity` 也必须改成 `KeywordHitSeverity`
- 增加非法 severity 的 API 测试

问题 2：诊断条件结果仍使用宽松字符串。

位置：

- `backend/app/schemas/diagnosis.py`
- `backend/app/services/diagnosis_service.py`
- `frontend/src/api/types.ts`

影响：

- 前端已将 `DiagnosisMatch.matched_conditions[].type/operator` 定义为冻结枚举
- 但后端 `DiagnosisConditionResult.type/operator` 仍是 `str`
- 如果模板引擎返回非法 condition type/operator，响应 schema 不会兜住

处理要求：

- 交给“故障模板与匹配引擎”优先处理
- 诊断结果里的 condition type/operator 必须复用冻结枚举
- `diagnosis_service` 需要在输出前标准化条件结果
- 增加非法 condition type/operator 不会进入成功响应的测试

### 14.3 继续派发顺序

现在可以继续派发后续任务。

第一批并行：

- “关键字库与白名单”
- “故障模板与匹配引擎”
- “巡检编排与检查入口”

第二批并行：

- “K8s 采集与证据抽取”

说明：

- “K8s 采集与证据抽取”可以与第一批并行，但必须限制在 provider 层
- 不允许它修改 `KeywordHit`、模板条件、白名单语义

最后执行：

- “前端工作台与人性化 UI”
- “整体质量验收”

### 14.4 给后续任务的共同要求

所有后续任务必须参考：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`
- `worklog/codex-contract-models-2026-07-11.md`

所有后续任务不得私自扩展以下共享字段：

- `InspectionTarget`
- `KeywordHit`
- `EvidenceBundle`
- `TemplateTarget`
- `TemplateCondition`
- `TemplateMatchResult`

如确实需要改共享契约，必须先更新：

- API 契约文档
- 后端 schema
- 前端类型
- 契约测试

## 15. 第一批并行任务 Review 结论与下一步指令

Review 时间：2026-07-11。

本轮 review 范围：

- `worklog/codex-inspection-entry-saved-targets-2026-07-11.md`
- `worklog/codex-keyword-whitelist-2026-07-11.md`
- `worklog/codex-fault-template-matching-engine-2026-07-11.md`
- `backend/app/engine/matcher.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/api/routes/templates.py`
- `backend/app/api/routes/saved_targets.py`
- `backend/app/providers/kubernetes_provider.py`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/WhitelistsPage.tsx`

验证结果：

- 后端：`python3 -m pytest -q backend/tests` 通过，`40 passed, 1 warning`
- 前端：`npm test -- --run` 通过，`7 files / 12 tests passed`
- 前端构建：`npm run build` 通过

### 15.1 总体结论

第一批并行任务已经推进了大量能力，但还不能进入最终“前端工作台与人性化 UI”收口。

原因：

- 模板匹配引擎仍有语义错误
- 诊断响应 schema 仍未完全使用冻结枚举
- 保存巡检对象和模板管理接口仍不完整
- 名称空间巡检页仍存在 demo 快捷对象和前端伪造日志命中
- K8s 单 Pod 巡检仍会扫描整个名称空间

下一步应先派返工任务，不要直接进入最终 UI 收口。

### 15.2 必须返工的问题

问题 1：模板 matcher 没有真正按 `operator` 执行。

位置：

- `backend/app/engine/matcher.py`

表现：

- `pod_status` 直接把 `expected_value` 转成 set。如果 `operator=equals` 且 `expected_value` 是字符串，会变成字符集合，导致无法匹配。
- `restart_count` 无视 `operator`，始终按 `>=` 判断。
- `related_object_status` 无视 `operator`，只看 statuses 列表。
- `log_keyword` 和 `event_keyword` 也没有严格校验 `contains` 语义。

处理要求：

- 交给“故障模板与匹配引擎”返工。
- 必须统一实现 `equals / in / contains / gte / lte`。
- 每种 condition type 都要覆盖合法 operator。
- 不支持的 condition type/operator 不能静默返回未命中，应给出可测试的失败结果或明确未支持状态。
- 补充 matcher 单测，覆盖：
  - `pod_status + equals + string`
  - `pod_status + in + list`
  - `restart_count + gte/lte/equals`
  - `event_keyword + contains`
  - `log_keyword` 只消费 `whitelisted=false` 的 `KeywordHit`

问题 2：诊断条件结果仍使用宽松字符串。

位置：

- `backend/app/schemas/diagnosis.py`
- `backend/app/services/diagnosis_service.py`

表现：

- `DiagnosisConditionResult.type` 仍是 `str`
- `DiagnosisConditionResult.operator` 仍是 `str`
- 这没有完全执行 API 契约冻结要求

处理要求：

- 交给“故障模板与匹配引擎”返工。
- `DiagnosisConditionResult.type` 必须复用 `TemplateConditionType`。
- `DiagnosisConditionResult.operator` 必须复用 `TemplateConditionOperator`。
- `DiagnosisResponse.status` 建议收紧为固定枚举：`matched / unmatched / llm_supplemented`。
- `diagnosis_service` 输出前必须标准化条件结果，不能把任意字符串透传给响应。

问题 3：名称空间巡检页仍会伪造日志命中，并且没有识别服务端白名单状态。

位置：

- `frontend/src/pages/NamespaceInspectionPage.tsx`

表现：

- 当 `selectedPod.log_hits` 为空时，页面会把 `log_summary` 每一行转成伪 `KeywordHit`。
- 页面判断忽略状态只看本地 `ignoredLogKeys`，没有把 `hit.whitelisted` 当成已忽略。
- 这会绕过关键字库和白名单契约，用户可能把整行日志误加入白名单关键字。

处理要求：

- 交给“前端工作台与人性化 UI”后续处理，但必须等模板 matcher 返工完成后再做整体 UI。
- 删除 `toKeywordHits` 伪造逻辑。
- 日志命中区只展示后端返回的 `log_hits`。
- `hit.whitelisted=true` 时按钮显示“白名单已生效”，且禁止再次忽略。
- 原始 `log_summary` 可以作为只读日志摘要展示，但不能当作关键字命中。

问题 4：名称空间巡检页仍有硬编码 demo 快捷对象。

位置：

- `frontend/src/pages/NamespaceInspectionPage.tsx`

表现：

- 页面仍包含 `demo-api / demo-worker / demo 全名称空间` 三个内置快捷对象。
- 这与“减少手动输入但必须可迁移、可保存”的产品目标冲突。

处理要求：

- 交给“前端工作台与人性化 UI”处理。
- 快捷对象只来自保存巡检对象接口。
- 如果没有保存对象，展示空状态和创建入口。
- 不允许继续以内置 demo 对象作为主要入口。

问题 5：K8s 单 Pod 巡检仍扫描整个名称空间。

位置：

- `backend/app/providers/kubernetes_provider.py`

表现：

- `run_pod_inspection` 仍调用 `run_namespace_inspection(namespace, None)` 再筛选 Pod。
- 大名称空间下会额外读取所有 Pod、Service、Ingress、DaemonSet、Secret。

处理要求：

- 交给“K8s 采集与证据抽取”返工。
- 使用 `read_namespaced_pod` 直接读取目标 Pod。
- 只读取该 Pod 相关事件、日志、前一次日志和必要关联资源。
- 如果为关联 Service 需要列表查询，应只在必要时做，不能把完整 namespace 巡检作为 Pod 巡检实现。

问题 6：模板管理接口还不完整。

位置：

- `backend/app/api/routes/templates.py`

表现：

- 已有列表、新增、编辑、删除。
- 仍缺少启用、停用、导入、导出。
- 模板 worklog 中也明确模板录入/编辑/导入导出 UI 仍未完成。

处理要求：

- 后端交给“故障模板与匹配引擎”补齐。
- 前端交给“前端工作台与人性化 UI”在后端接口稳定后实现。

问题 7：保存巡检对象接口还不完整。

位置：

- `backend/app/api/routes/saved_targets.py`

表现：

- 已有列表、新增、删除。
- 仍缺少更新、导入、导出。
- 前端 hook 也只有保存和列表，没有删除、更新、导入、导出。

处理要求：

- 交给“巡检编排与检查入口”继续补齐。
- 首页和巡检页后续只能依赖保存对象接口，不应再写死 demo 快捷对象。

### 15.3 下一步派发顺序

下一步不要派“整体质量验收”，也不要直接派最终 UI 收口。

第一优先级，必须先返工：

- “故障模板与匹配引擎”
- “K8s 采集与证据抽取”
- “巡检编排与检查入口”

第二优先级，接口稳定后派发：

- “前端工作台与人性化 UI”

最后执行：

- “整体质量验收”

### 15.4 给“故障模板与匹配引擎”的继续指令

参考文件：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/engine/matcher.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/schemas/diagnosis.py`
- `backend/tests/test_matcher.py`
- `backend/tests/test_diagnosis_api.py`

必须完成：

- 修正 matcher operator 语义
- 收紧诊断响应里的 condition type/operator
- 补齐模板启用、停用、导入、导出后端接口
- 保持 `log_keyword` 只消费 `KeywordHit`
- 保持 `whitelisted=true` 不参与模板命中

验收命令：

- `python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py`
- `python3 -m pytest -q backend/tests`

### 15.5 给“K8s 采集与证据抽取”的继续指令

参考文件：

- `backend/app/providers/kubernetes_provider.py`
- `backend/app/providers/base.py`
- `backend/app/providers/mock_provider.py`
- `backend/tests/test_kubernetes_provider.py`

必须完成：

- `run_pod_inspection` 改为直接读取单 Pod
- 不再通过完整 namespace 巡检实现单 Pod 巡检
- 保持 provider 不生成最终 `log_hits`
- `describe_summary` 继续增强，但不要改变 API 契约字段

验收命令：

- `python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py`
- `python3 -m pytest -q backend/tests`

### 15.6 给“巡检编排与检查入口”的继续指令

参考文件：

- `backend/app/api/routes/saved_targets.py`
- `backend/app/services/saved_target_service.py`
- `backend/app/schemas/saved_target.py`
- `backend/tests/test_saved_targets_api.py`

必须完成：

- 保存巡检对象增加更新接口
- 保存巡检对象增加导入接口
- 保存巡检对象增加导出接口
- 补齐对应测试
- 不要扩散 `InspectionTarget` 共享字段

验收命令：

- `python3 -m pytest -q backend/tests/test_saved_targets_api.py backend/tests/test_inspection_api.py`
- `python3 -m pytest -q backend/tests`

### 15.7 给“前端工作台与人性化 UI”的等待条件

暂时不要做最终 UI 收口，等待以下任务完成：

- “故障模板与匹配引擎”完成 matcher 和模板管理接口返工
- “巡检编排与检查入口”完成保存对象更新、导入、导出
- “K8s 采集与证据抽取”完成单 Pod 直接采集

之后再做：

- 删除命名空间巡检页硬编码 demo 快捷对象
- 删除前端伪造 `KeywordHit` 逻辑
- 首页接入真实保存对象
- 保存对象支持编辑、删除、导入、导出
- 模板录入器 UI
- 白名单/关键字导入导出 UI

### 15.8 本轮 review 后的质量门禁

后续每个任务完成后，必须在 worklog 中写清楚：

- 修改了哪些文件
- 跑了哪些测试
- 哪些问题仍未完成
- 是否改动共享契约

总控在进入最终 UI 收口前必须确认：

- 后端全量测试通过
- 前端测试和构建通过
- 没有新增硬编码 demo 入口
- 模板条件 operator 单测覆盖完整
- 单 Pod 巡检不再扫描整个名称空间

## 16. 第三轮 Review 结论与下一步指令

Review 时间：2026-07-11

当前结论：

- “故障模板与匹配引擎”后端返工已基本完成，`matcher` 已支持 `joint_rule.operator` 的 `AND/OR` 语义，`log_keyword` 已跳过 `whitelisted=true` 命中，模板后端已补齐启用、停用、导入、导出接口。
- “K8s 采集与证据抽取”关键返工已完成，单 Pod 巡检已改为 `read_namespaced_pod` 直接读取指定 Pod，不再通过完整名称空间巡检兜底。
- “巡检编排与检查入口”保存对象后端能力已补齐，已有创建、更新、删除、导入、导出接口；名称空间页已接入部分保存对象能力。
- 当前阻塞点不在后端主流程，而在前端工作台和最终验收。不要再让后端 agent 盲目扩展字段或重构契约。

本轮已验证：

- `python3 -m pytest -q backend/tests`：47 passed，1 warning。
- `cd frontend && npm test -- --run`：7 files / 13 tests passed。
- `cd frontend && npm run build`：构建成功。

### 16.1 仍需修正的问题

问题 1：名称空间巡检页仍有硬编码 demo 快捷对象。

- 位置：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 表现：`quickTargets` 仍写死 `demo-api`、`demo-worker`、`demo 全名称空间`。
- 风险：用户会误以为这是实际环境数据，且违背“不能每次手动输入，保存后复用”的核心目标。
- 处理：只能展示接口返回的保存对象；如果没有保存对象，显示空状态和引导保存，不允许内置 demo 环境入口。

问题 2：名称空间巡检页仍把 `log_summary` 伪造成 `KeywordHit`。

- 位置：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 表现：`toKeywordHits` 会把每行日志摘要包装成 warning 级别关键字命中。
- 风险：会制造假告警，绕过后端关键字库和白名单规则，影响故障模板匹配可信度。
- 处理：前端只能展示后端返回的 `pod.log_hits`；如果没有命中，则展示原始日志摘要文本，不允许生成新的 `KeywordHit`。

问题 3：名称空间巡检页未正确展示已被白名单命中的日志项。

- 位置：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 表现：UI 只判断本地 `ignoredLogKeys`，没有把 `hit.whitelisted` 作为已忽略状态。
- 风险：已在后端白名单生效的命中仍可能显示为可忽略，用户体验和实际状态不一致。
- 处理：与 `PodInspectionPage.tsx` 保持一致，`ignored = hit.whitelisted || ignoredLogKeys.includes(hitKey)`，按钮文案也要区分“白名单已生效”和“已忽略”。

问题 4：模板页仍只是展示，没有真正的故障模板录入入口。

- 位置：`frontend/src/pages/TemplatesPage.tsx`、`frontend/src/features/templates/useTemplates.ts`、`frontend/src/api/client.ts`
- 表现：只能 list 模板，不能 create/update/delete/enable/disable/import/export。
- 风险：用户明确要求“系统要有录入故障的入口”，当前 UI 不满足核心需求。
- 处理：模板页必须提供面向运维人员的可视化录入器，不要求用户手写 JSON。

问题 5：关键字库与白名单页缺少导入、导出、编辑、删除 UI。

- 位置：`frontend/src/pages/WhitelistsPage.tsx`、`frontend/src/features/whitelists/*`、`frontend/src/api/client.ts`
- 表现：当前只支持新增和启停。
- 风险：无法满足“能导入导出供其他环境用”，也不利于维护已有规则。
- 处理：补齐关键字库和白名单的导入、导出、编辑、删除入口。

问题 6：保存巡检对象前端能力未完整闭环。

- 位置：`frontend/src/features/inspections/useSavedInspectionTargets.ts`、`frontend/src/pages/NamespaceInspectionPage.tsx`、`frontend/src/pages/PodInspectionPage.tsx`
- 表现：后端已有删除接口，但前端没有删除；hook 当前强制保存为 `namespace` 类型，Pod 页面没有保存为巡检对象入口。
- 风险：Pod 巡检无法沉淀常用对象，保存对象管理不完整。
- 处理：hook 支持 namespace/pod 两种类型；名称空间页和 Pod 页都能保存、编辑、删除、导入、导出。

问题 7：本地运行产物不能进入提交。

- 位置：仓库根目录当前存在 `k8s_inspector.db`、`root-test.db`、`subpath-test.db`。
- 风险：测试数据库进入版本库会污染环境。
- 处理：最终提交前清理或加入忽略规则；清理动作由负责提交的会话执行，不要在业务 agent 中随意删除。

### 16.2 下一步派发顺序

第一批可并行：

- “前端工作台与人性化 UI”
- “关键字库与白名单”

第二批必须等待第一批完成后执行：

- “故障模板与匹配引擎”

第三批必须等待 UI、模板、白名单全部完成后执行：

- “统一契约与数据模型”
- “整体质量验收”

不要再启动新的“K8s 采集与证据抽取”任务，除非后续验收发现真实集群采集缺陷。

### 16.3 给“前端工作台与人性化 UI”的继续指令

让“前端工作台与人性化 UI”参考以下文件开发：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `docs/superpowers/specs/2026-07-06-k8s-inspector-realignment-design.md`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/TemplatesPage.tsx`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`

必须完成：

- 删除名称空间巡检页所有硬编码 demo 快捷对象。
- 删除 `toKeywordHits` 这类前端伪造 `KeywordHit` 的逻辑。
- 名称空间巡检页按 `hit.whitelisted` 展示“白名单已生效”，行为与 Pod 巡检页一致。
- 首页展示真实保存巡检对象和最近巡检入口，不展示假数据。
- 保存巡检对象管理完整支持创建、编辑、删除、导入、导出。
- Pod 巡检页支持保存当前 Pod 为巡检对象。
- 巡检结果页要突出异常 Pod、describe 摘要、事件、关键字命中、原始日志摘要之间的边界，不允许混成一个告警列表。
- UI 文案要面向运维用户，避免暴露内部字段名作为主要操作入口。

边界：

- 不修改后端契约字段。
- 不在前端实现模板匹配逻辑。
- 不在前端生成关键字命中。
- 不新增 demo/mock 快捷入口。

验收命令：

- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 删除了哪些硬编码入口。
- 哪些页面接入了真实接口。
- 保存对象 namespace/pod 两种类型分别如何操作。
- 手工验证了哪些主要交互路径。

### 16.4 给“关键字库与白名单”的继续指令

让“关键字库与白名单”参考以下文件开发：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/api/routes/keywords.py`
- `backend/app/api/routes/whitelists.py`
- `backend/app/services/keyword_service.py`
- `backend/app/services/whitelist_service.py`
- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/features/whitelists/useKeywords.ts`
- `frontend/src/features/whitelists/useWhitelists.ts`
- `frontend/src/api/client.ts`

必须完成：

- 前端补齐关键字库编辑、删除、导入、导出。
- 前端补齐白名单编辑、删除、导入、导出。
- 导入使用文本框 JSON 即可，后续可再做文件上传。
- 导出允许复制 JSON，字段必须与后端接口一致。
- 白名单列表要清楚展示 namespace、label selector、pod name pattern、container、keyword、enabled、note。
- 忽略日志命中后生成的白名单必须能在白名单页看到并停用。

边界：

- 不改变 `KeywordHit`、`Whitelist` 后端模型语义。
- 不把白名单判断放到前端。
- 不在本任务里做故障模板 UI。

验收命令：

- `python3 -m pytest -q backend/tests/test_whitelist_api.py backend/tests/test_inspection_api.py`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 支持了哪些 CRUD 和导入导出能力。
- 忽略报错到白名单的链路是否可见。
- 是否改动 API 契约；如未改动也要明确说明。

### 16.5 给“故障模板与匹配引擎”的继续指令

让“故障模板与匹配引擎”在第一批 UI 和白名单任务完成后再启动，参考以下文件开发：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/engine/matcher.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/api/routes/templates.py`
- `frontend/src/pages/TemplatesPage.tsx`
- `frontend/src/features/templates/useTemplates.ts`
- `frontend/src/api/client.ts`
- `backend/tests/test_matcher.py`
- `backend/tests/test_template_api.py`

必须完成：

- 前端模板页支持创建、编辑、删除、启用、停用、导入、导出。
- 模板录入器必须支持多个对象组。
- 每个对象组支持 namespace、label selector、Pod 名称模式、资源范围。
- 条件块至少支持 `log_keyword`、`pod_status`、`restart_count`、`event_keyword`、`related_object_status`。
- 条件块 operator 使用后端契约，不允许前端自造枚举。
- joint rule 至少支持 `AND`、`OR`。
- 模板录入时要能填写 reason、suggestion、command、risk_note。
- 模板列表要展示启用状态、对象组摘要、条件摘要和处理建议。

边界：

- matcher 后端当前不做大重构，除非新增测试证明现有逻辑错误。
- 不让用户直接编辑大段 JSON 作为唯一入口；JSON 导入导出只能作为迁移能力。
- 不在模板页触发真实 K8s 巡检；模板匹配入口仍走诊断接口。

验收命令：

- `python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_template_api.py backend/tests/test_diagnosis_api.py`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 模板录入器支持哪些条件类型和 operator。
- 导入导出的 payload 示例。
- 是否覆盖“多个 Pod 匹配时只要一个 Pod 满足即符合”的规则。

### 16.6 给“统一契约与数据模型”的收口指令

让“统一契约与数据模型”在 UI、白名单、模板任务完成后再启动，参考以下文件：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `frontend/src/api/types.ts`

必须完成：

- 核对后端 Pydantic schema 与前端 TypeScript 类型是否一致。
- 核对接口是否仍兼容 `targets` 与 `target_groups` 的历史字段。
- 清理文档中已经过期的“等待返工”描述，保留最终状态。
- 如发现契约不一致，只做最小修正，并补测试。

边界：

- 不做 UI 重构。
- 不改 matcher 语义。
- 不新增业务字段，除非已有页面或测试明确需要。

验收命令：

- `python3 -m pytest -q backend/tests/test_contract_models.py backend/tests`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

### 16.7 给“整体质量验收”的最终指令

让“整体质量验收”最后启动，不能提前。

必须完成：

- 后端全量测试：`python3 -m pytest -q backend/tests`
- 前端测试：`cd frontend && npm test -- --run`
- 前端构建：`cd frontend && npm run build`
- 检查 `git status --short`，确认没有测试数据库、构建缓存、临时文件准备进入提交。
- 手工走通以下路径：
- 名称空间巡检：可全名称空间巡检，也可 label selector 巡检。
- Pod 巡检：只检查指定 Pod，异常时展示 describe、event、log、keyword hit。
- 忽略日志命中：点击后生成白名单，下一次展示为已忽略。
- 保存巡检对象：namespace/pod 均可保存、编辑、删除、导入、导出。
- 故障模板：可录入多对象组、多条件、AND/OR，手动触发诊断后能返回匹配和未匹配条件。
- 关键字库和白名单：可增删改、启停、导入、导出。

最终 worklog 必须包含：

- 测试命令和结果。
- 手工验收路径和结果。
- 剩余风险。
- 是否存在未提交的非代码产物。

## 17. 第四轮 Review 后的下一步指令

Review 时间：2026-07-12

当前判断：

- “关键字库与白名单”前端能力已经看到编辑、删除、导入、导出、启停入口，下一步不再优先派新功能，只等待最终验收。
- “故障模板与匹配引擎”前端能力已经看到模板录入器、对象组、条件块、导入、导出、删除、启停入口，下一步不再继续扩展模板功能，只等待最终验收。
- “统一契约与数据模型”发现的两个类型问题已修正：`DiagnosisResponse.direction` 收紧为 `template_check`，`target_groups` 兼容输出改为 `object_scope`。
- 当前还不能进入最终质量验收，因为名称空间巡检页仍保留两个明确问题：硬编码 demo 快捷对象和前端伪造 `KeywordHit`。

### 17.1 当前必须先处理的阻塞问题

阻塞 1：名称空间巡检页仍有硬编码 demo 快捷对象。

- 文件：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 证据：仍存在 `quickTargets`。
- 要求：删除所有内置 demo 快捷对象，只展示后端保存对象接口返回的数据。

阻塞 2：名称空间巡检页仍把日志摘要伪造成关键字命中。

- 文件：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 证据：仍存在 `toKeywordHits`，且 `logHits` 使用 `selectedPod.log_hits` 为空时回退到 `toKeywordHits(selectedPod.log_summary)`。
- 要求：前端不得生成 `KeywordHit`。没有后端关键字命中时，只展示“原始日志摘要”文本。

阻塞 3：名称空间巡检页仍没有按后端白名单状态展示命中。

- 文件：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 证据：忽略状态仍只判断 `ignoredLogKeys.includes(hitKey)`。
- 要求：与 `PodInspectionPage.tsx` 保持一致，`ignored = hit.whitelisted || ignoredLogKeys.includes(hitKey)`，按钮文案区分“白名单已生效 / 已忽略 / 处理中 / 忽略此报错”。

### 17.2 立即派发给“前端工作台与人性化 UI”

让“前端工作台与人性化 UI”只处理名称空间巡检页返工，不要再扩模板、白名单或后端接口。

参考文件：

- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`
- `frontend/src/api/types.ts`
- `docs/superpowers/plans/2026-07-11-api-contract.md`

必须完成：

- 删除 `quickTargets` 常量和所有相关渲染。
- 删除 `toKeywordHits` 函数和所有相关调用。
- `selectedPod.log_hits` 为空时，不展示假命中；改为展示原始 `selectedPod.log_summary`，标题明确为“原始日志摘要”。
- `selectedPod.log_hits` 非空时，展示“关键字命中”，并清楚标出 keyword、category、severity、matched_text、container。
- `hit.whitelisted=true` 时，卡片弱化展示，按钮显示“白名单已生效”且禁用。
- 用户本次点击忽略成功后，按钮显示“已忽略”，并提示后续巡检会自动忽略。
- 保存对象区域只能来自 `useSavedInspectionTargets()` 的真实数据。
- 如果没有保存对象，显示“暂无保存对象，保存当前巡检范围后可复用”，不能显示 demo。
- 如 hook 已支持删除，则名称空间页补一个删除入口；如 hook 仍不支持删除，本次补齐 hook 和页面删除入口。
- 测试必须覆盖：无保存对象空状态、无 `log_hits` 时不生成假命中、`hit.whitelisted=true` 的显示和按钮禁用。

边界：

- 不改后端接口。
- 不改模板页。
- 不改白名单页。
- 不新增 demo/mock 快捷入口。
- 不把日志摘要当作告警。

验收命令：

- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 删除了哪些硬编码/伪造逻辑。
- 新增或修改了哪些测试。
- 名称空间页和 Pod 页的忽略交互是否一致。
- 是否改动 API 契约；预期是不改。

### 17.3 “统一契约与数据模型”暂不继续派发

暂时不要再派“统一契约与数据模型”继续改代码。

原因：

- 本轮契约发现的问题已经修正。
- 当前剩余阻塞是页面行为问题，不是契约问题。
- 等“前端工作台与人性化 UI”完成名称空间页返工后，再让“统一契约与数据模型”做最终轻量复核。

最终轻量复核内容：

- `frontend/src/api/types.ts` 与 `backend/app/schemas/*` 是否仍一致。
- `target_groups` 兼容输出是否仍只按 `object_scope` 使用。
- 文档是否没有过期的返工指令误导后续 agent。

### 17.4 “整体质量验收”的等待条件

现在还不能派“整体质量验收”。

必须等以下条件全部满足后再派：

- 名称空间巡检页没有 `quickTargets`。
- 名称空间巡检页没有 `toKeywordHits`。
- 名称空间巡检页按 `hit.whitelisted` 展示白名单状态。
- 前端测试和构建通过。
- 后端全量测试通过。

满足后，让“整体质量验收”执行：

- `python3 -m pytest -q backend/tests`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`
- 检查 `git status --short`，明确哪些是业务代码、哪些是 worklog、哪些是本地运行产物。
- 确认 `k8s_inspector.db`、`root-test.db`、`subpath-test.db` 不会进入提交。
- 手工验收名称空间巡检、Pod 巡检、保存对象、忽略报错到白名单、关键字导入导出、白名单导入导出、模板录入、模板诊断。

### 17.5 你下一步应该怎么分配

下一条指令直接发给“前端工作台与人性化 UI”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 17 节，只处理名称空间巡检页返工。删除 `quickTargets` 和 `toKeywordHits`，禁止前端伪造 `KeywordHit`，按 `hit.whitelisted` 展示白名单状态，补齐相关测试。不要改后端、模板页、白名单页。完成后写 worklog，并跑 `cd frontend && npm test -- --run` 和 `cd frontend && npm run build`。

等该 agent 完成后，再回来让我 review。

## 18. 第五轮 Review 结论与下一步指令

Review 时间：2026-07-12

Review 对象：

- “前端工作台与人性化 UI”第 17 节名称空间巡检页返工结果。

验证结果：

- `cd frontend && npm test -- --run`：7 files passed，15 tests passed。
- `cd frontend && npm run build`：构建成功。
- `python3 -m pytest -q backend/tests`：47 passed，1 warning。

本轮结论：

- 第 17 节列出的 3 个阻塞点已经处理完成。
- 名称空间巡检页已删除 `quickTargets`。
- 名称空间巡检页已删除 `toKeywordHits`。
- `selectedPod.log_hits` 为空时展示“原始日志摘要”，不再伪造关键字命中。
- `hit.whitelisted=true` 时显示“白名单已生效”并禁用按钮。
- 保存巡检对象已补齐删除入口。

### 18.1 本轮 Review 发现的剩余风险

风险 1：保存对象类型分流仍不完整。

- 文件：`frontend/src/pages/NamespaceInspectionPage.tsx`
- 现状：名称空间巡检页会展示 `target_type === "pod"` 的保存对象，并标记为“Pod 巡检对象”。
- 问题：点击该对象的“使用”按钮时，当前仍走名称空间巡检逻辑，只使用 `namespace + label_selector`，没有使用 `pod_name`，也不会跳转 Pod 巡检页。
- 影响：如果用户导入或后续保存了 Pod 类型巡检对象，在名称空间页点击“使用”会产生不符合预期的巡检。
- 定性：不影响第 17 节验收，但影响最终产品一致性，进入整体质量验收前必须处理。

### 18.2 立即派发给“前端工作台与人性化 UI”的小收口

让“前端工作台与人性化 UI”只做保存对象类型分流，不要改后端、模板页、白名单页。

参考文件：

- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/routes/index.tsx`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`
- `frontend/src/api/types.ts`

必须完成以下方案之一，优先选方案 A。

方案 A，推荐：

- 名称空间巡检页只展示 `target_type === "namespace"` 的保存对象。
- Pod 巡检页展示 `target_type === "pod"` 的保存对象。
- Pod 巡检页支持保存当前 `namespace + pod_name` 为 Pod 巡检对象。
- Pod 巡检页支持使用、编辑、删除、导入、导出 Pod 巡检对象。

方案 B，如果时间紧：

- 名称空间巡检页过滤掉 `target_type === "pod"` 的保存对象。
- 页面提示“Pod 巡检对象请到 Pod 巡检页使用”。
- Pod 巡检对象完整管理可以留给下一轮，但不得在名称空间页错误执行。

边界：

- 不改后端接口。
- 不改保存对象 schema。
- 不把 Pod 保存对象当 namespace 对象执行。
- 不新增 demo/mock 数据。

测试要求：

- 名称空间页不会展示 Pod 类型保存对象的“使用”按钮。
- 如果选择方案 A，Pod 页能保存并使用 Pod 类型保存对象。
- 现有名称空间保存对象测试继续通过。

验收命令：

- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 选择了方案 A 还是方案 B。
- namespace/pod 两类保存对象分别在哪个页面展示和使用。
- 是否改动 API 契约；预期是不改。

### 18.3 下一步派发建议

下一条指令发给“前端工作台与人性化 UI”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 18 节，只处理保存对象类型分流。优先做方案 A：名称空间页只展示 namespace 保存对象；Pod 页展示、保存、使用、编辑、删除、导入、导出 pod 保存对象。不要改后端、模板页、白名单页，不要新增 demo 数据。完成后写 worklog，并跑 `cd frontend && npm test -- --run` 和 `cd frontend && npm run build`。

如果该小收口完成并通过 review，再派“统一契约与数据模型”做最终轻量复核，然后派“整体质量验收”。

## 19. 第六轮 Review 结论与下一步指令

Review 时间：2026-07-12

Review 对象：

- “前端工作台与人性化 UI”第 18 节保存对象类型分流结果。

验证结果：

- `cd frontend && npm test -- --run`：7 files passed，17 tests passed。
- `cd frontend && npm run build`：构建成功。
- `python3 -m pytest -q backend/tests`：47 passed，1 warning。

本轮结论：

- 第 18 节方案 A 的主流程已经完成。
- `useSavedInspectionTargets("namespace")` 和 `useSavedInspectionTargets("pod")` 已按类型加载和展示。
- 名称空间巡检页只展示 namespace 类型保存对象。
- Pod 巡检页只展示 pod 类型保存对象。
- Pod 巡检页已支持保存、使用、编辑、删除、导出、导入 pod 保存对象。

### 19.1 本轮 Review 发现的剩余问题

问题：保存对象导入在提交后端前没有按当前页面类型过滤。

- 文件：`frontend/src/features/inspections/useSavedInspectionTargets.ts`
- 位置：`importTargets`
- 现状：`importTargets(payload)` 会把用户粘贴的完整 payload 原样提交给 `/inspection-targets/import`，然后只把后端返回结果按当前 `targetType` 过滤回填到页面。
- 风险：如果用户在名称空间页粘贴包含 pod 对象的 JSON，pod 对象会被创建到后端；如果用户在 Pod 页粘贴 namespace 对象，也会被创建到后端。页面虽然不展示，但数据库已经被污染。
- 定性：这是类型分流的最后一个质量缺口，进入整体质量验收前必须修。

### 19.2 立即派发给“前端工作台与人性化 UI”的最小修复

让“前端工作台与人性化 UI”只修保存对象导入过滤，不要改后端、模板页、白名单页。

参考文件：

- `frontend/src/features/inspections/useSavedInspectionTargets.ts`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`
- `frontend/src/pages/PodInspectionPage.test.tsx`

必须完成：

- `importTargets` 在调用 `importSavedInspectionTargets` 之前，先过滤 `payload`，只提交 `target_type === targetType` 的对象。
- 如果过滤后为空，不调用后端导入接口，返回空数组，并在页面给出“不包含当前页面可导入的对象”之类的提示。
- 名称空间页导入消息显示实际导入的 namespace 对象数量，不显示原始 JSON 数量。
- Pod 页导入消息显示实际导入的 pod 对象数量，不显示原始 JSON 数量。
- 增加测试覆盖：在 namespace 页导入混合 JSON 时，不会把 pod 对象发给后端；在 Pod 页导入混合 JSON 时，不会把 namespace 对象发给后端。

边界：

- 不改后端接口。
- 不改保存对象 schema。
- 不新增 demo/mock 数据。
- 不改变导出行为；导出继续只导出当前页面类型。

验收命令：

- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 导入前过滤逻辑如何处理。
- 空导入如何提示用户。
- 是否改动 API 契约；预期是不改。

### 19.3 下一步派发建议

下一条指令发给“前端工作台与人性化 UI”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 19 节，只修保存对象导入过滤。`importTargets` 必须在提交后端前只保留当前页面 `targetType` 的对象；空导入不调用后端并给用户提示；namespace/pod 页导入消息显示实际导入数量。不要改后端、模板页、白名单页，不要改导出行为。完成后写 worklog，并跑 `cd frontend && npm test -- --run` 和 `cd frontend && npm run build`。

该问题修完并通过 review 后，再派“统一契约与数据模型”做最终轻量复核。

## 20. 第七轮 Review 结论与下一步指令

Review 时间：2026-07-12

Review 对象：

- “前端工作台与人性化 UI”第 19 节保存对象导入过滤结果。

验证结果：

- `cd frontend && npm test -- --run`：7 files passed，19 tests passed。
- `cd frontend && npm run build`：构建成功。
- `python3 -m pytest -q backend/tests`：47 passed，1 warning。

本轮结论：

- 第 19 节问题已修复。
- `importTargets` 已在调用后端导入接口前按当前 `targetType` 过滤。
- 空导入不再调用后端。
- 名称空间页和 Pod 页都按实际导入数量展示提示。
- 保存对象 namespace/pod 分流目前可以进入最终契约复核。

### 20.1 下一步派发给“统一契约与数据模型”

让“统一契约与数据模型”做最终轻量复核，不要扩新功能。

参考文件：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/saved_target.py`
- `backend/app/schemas/keyword.py`
- `backend/app/schemas/whitelist.py`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`

必须完成：

- 核对后端 Pydantic schema 与前端 TypeScript 类型是否一致。
- 核对 `InspectionTarget.type`、`SavedInspectionTarget.target_type`、`KeywordHit.severity`、`TemplateCondition.condition_type`、`TemplateCondition.operator`、`DiagnosisResponse.direction` 是否仍为收紧枚举。
- 核对 `FaultTemplate.targets` 与 `target_groups` 兼容输入/输出是否与文档一致。
- 核对保存对象导入/导出 payload 是否与后端 `SavedInspectionTargetCreate/Read` 一致。
- 核对前端 API client 是否没有遗漏后端已存在的关键 CRUD/import/export 接口。
- 清理或标注文档中过期的返工描述，避免后续 agent 被旧章节误导。不要删除历史 review 记录，但可以新增“当前最终状态”说明。

边界：

- 不做 UI 重构。
- 不改 matcher 语义。
- 不改后端接口路径。
- 不新增业务字段。
- 只有发现明确契约不一致时，才做最小代码修正和测试。

验收命令：

- `python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_template_api.py backend/tests/test_saved_targets_api.py backend/tests/test_whitelist_api.py`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

worklog 必须写清：

- 核对了哪些契约项。
- 发现了哪些不一致。
- 是否做了代码修正。
- 是否存在仍需整体质量验收关注的残余风险。

### 20.2 派发文本

下一条指令发给“统一契约与数据模型”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 20 节，做最终轻量契约复核。重点核对后端 Pydantic schema、前端 `api/types.ts`、`api/client.ts`、保存对象导入/导出、模板 `targets/target_groups` 兼容、诊断 direction 枚举。不要扩新功能，不做 UI 重构，不改 matcher 语义。只有发现明确契约不一致时才做最小修正并补测试。完成后写 worklog，并跑第 20 节列出的验收命令。

如果该复核通过，再派“整体质量验收”。

### 20.3 当前最终状态说明

本节用于补充说明当前最终轻量契约复核后的状态，避免后续 agent 被更早章节中的历史返工描述误导。

截至 2026-07-12，本轮轻量契约复核确认：

- 后端 Pydantic schema 与前端 `frontend/src/api/types.ts` 共享字段已对齐
- `InspectionTarget.type` 已保持收紧枚举
- `SavedInspectionTarget.target_type` 已保持收紧枚举
- `KeywordHit.severity` 已保持收紧枚举
- `TemplateCondition.condition_type` 已保持收紧枚举
- `TemplateCondition.operator` 已保持收紧枚举
- `DiagnosisResponse.direction` 已收紧为 `template_check`
- `FaultTemplate.targets` 仍是主字段
- `target_groups` 仍仅作为兼容输入/兼容输出保留
- 保存对象导入/导出链路已与 `SavedInspectionTargetCreate/Read` 契约保持一致
- 前端 `api/client.ts` 已覆盖保存对象、模板、关键字、白名单的关键 CRUD / import / export / enable / disable 接口

说明：

- 第 14 节、第 15 节中关于“诊断 direction 宽松字符串”“前端 `target_groups` 兼容结构未收口”等描述属于历史 review 结论
- 历史记录保留用于追踪问题来源，不代表当前仓库最新状态
- 后续 agent 做实现或验收时，应优先以：
  - `docs/superpowers/plans/2026-07-11-api-contract.md`
  - 本文档第 20 节
  - 最新 worklog
  作为当前判断依据

## 21. 第八轮 Review 结论与下一步指令

Review 时间：2026-07-12

Review 对象：

- “统一契约与数据模型”第 20 节最终轻量契约复核结果。

验证结果：

- `python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_template_api.py backend/tests/test_saved_targets_api.py backend/tests/test_whitelist_api.py`：23 passed，1 warning。
- `cd frontend && npm test -- --run`：7 files passed，19 tests passed。
- `cd frontend && npm run build`：构建成功。

本轮结论：

- 代码层面的共享契约主路径基本通过。
- 前端 `api/types.ts` 与后端主要 schema 当前没有发现阻塞级不一致。
- `DiagnosisResponse.direction`、`SavedInspectionTarget.target_type`、`KeywordHit.severity`、`TemplateCondition.condition_type/operator` 均已收紧。
- 保存对象导入/导出、模板 CRUD/import/export、关键字/白名单 CRUD/import/export 的 client 覆盖当前可接受。

### 21.1 本轮 Review 发现的问题

问题：契约文档对 `TemplateTarget` 兼容输入的描述不准确。

- 文件：`docs/superpowers/plans/2026-07-11-api-contract.md`
- 现有描述：`TemplateTarget` 自身只直接兼容 `scopes`，`ref/name/object_scope` 是 `FaultTemplate.target_groups` 层兼容。
- 实际代码：`backend/app/schemas/common.py` 中 `TemplateTarget.target_ref` 直接支持 `target_ref/ref`，`pod_name_pattern` 直接支持 `pod_name_pattern/name`，`resource_scope` 直接支持 `resource_scope/scopes`。
- 实际代码：`object_scope` 不是 `TemplateTarget` 的直接输入 alias，而是 `TemplateTarget` 的 computed output；`FaultTemplate` 读取旧 `target_groups` 时会把 `object_scope` 归一到 `resource_scope`。
- 风险：后续 agent 读文档会误以为标准 `targets` 不能输入 `ref/name`，或误解 `object_scope` 所在层级。
- 定性：文档级问题，不影响当前测试，但会影响后续维护质量。进入整体质量验收前建议先修正。

### 21.2 立即派发给“统一契约与数据模型”的文档级收口

让“统一契约与数据模型”只修契约文档，不改代码。

参考文件：

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `backend/app/schemas/common.py`
- `backend/app/schemas/template.py`
- `frontend/src/api/types.ts`

必须完成：

- 修正 `TemplateTarget` 章节：
- 明确 `TemplateTarget` 直接兼容输入为 `ref -> target_ref`、`name -> pod_name_pattern`、`scopes -> resource_scope`。
- 明确 `object_scope` 不是 `TemplateTarget` 的直接输入 alias。
- 明确 `object_scope` 在 `TemplateTarget` 上是计算输出，取 `resource_scope[0]`。
- 明确 `FaultTemplate.target_groups` 兼容输入可使用 `ref/name/object_scope`，其中 `object_scope` 会在 `FaultTemplate` 归一化阶段转成 `resource_scope`。
- 不删除历史 review 章节，只修当前契约文档的描述。

边界：

- 不改后端 schema。
- 不改前端类型。
- 不改测试。
- 不扩展新的兼容字段。

验收命令：

- `python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_template_api.py`

worklog 必须写清：

- 修改了哪几条文档说明。
- 是否改动代码；预期是不改。
- 是否仍存在契约歧义。

### 21.3 下一步派发建议

下一条指令发给“统一契约与数据模型”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 21 节，只做契约文档收口。修正 `docs/superpowers/plans/2026-07-11-api-contract.md` 中 `TemplateTarget` 兼容输入说明：`ref/name/scopes` 是 `TemplateTarget` 直接兼容输入；`object_scope` 不是直接输入 alias，而是计算输出；`FaultTemplate.target_groups` 的 `object_scope` 会归一化为 `resource_scope`。不要改代码，不要扩字段。完成后写 worklog，并跑第 21 节验收命令。

该文档收口完成并通过 review 后，再派“整体质量验收”。

## 22. 第九轮 Review 结论与最终验收指令

Review 时间：2026-07-12

Review 对象：

- “统一契约与数据模型”第 21 节契约文档收口结果。

验证结果：

- `python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_template_api.py`：10 passed，1 warning。

本轮结论：

- `docs/superpowers/plans/2026-07-11-api-contract.md` 中 `TemplateTarget` 兼容输入说明已修正。
- 文档已明确 `ref/name/scopes` 是 `TemplateTarget` 直接兼容输入。
- 文档已明确 `object_scope` 不是 `TemplateTarget` 直接输入 alias，而是计算输出。
- 文档已明确 `FaultTemplate.target_groups.object_scope` 会在归一化阶段转成 `targets[].resource_scope`。
- 本轮未改代码，符合第 21 节边界。
- 当前可以派发“整体质量验收”。

### 22.1 派发给“整体质量验收”

让“整体质量验收”做最终全链路验收，不再新增功能。

参考文件：

- `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`
- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `docs/superpowers/specs/2026-07-06-k8s-inspector-realignment-design.md`
- `worklog/`
- `backend/tests/`
- `frontend/src/pages/`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`

必须完成：

- 后端全量测试。
- 前端全量测试。
- 前端生产构建。
- 检查工作区状态，明确哪些是业务代码、哪些是文档、哪些是 worklog、哪些是本地运行产物。
- 确认测试数据库和本地运行产物不会进入提交。
- 手工或测试级别走通核心用户路径。

必跑命令：

- `python3 -m pytest -q backend/tests`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`
- `git status --short`

必须重点验收的用户路径：

- 名称空间巡检：支持全名称空间巡检和 label selector 巡检。
- 名称空间巡检结果：异常 Pod 优先，展示 describe、事件、关键字命中、原始日志摘要，且不伪造 `KeywordHit`。
- Pod 巡检：只巡检指定 Pod，不扫描整个名称空间。
- 忽略日志命中：点击后创建白名单；后续 `hit.whitelisted=true` 时显示“白名单已生效”并禁用按钮。
- 保存巡检对象：namespace/pod 两类对象分流正确，不互相误用。
- 保存对象导入：导入前按当前页面类型过滤，空导入不调用后端。
- 关键字库：支持新增、编辑、删除、启停、导入、导出。
- 白名单：支持新增、编辑、删除、启停、导入、导出；忽略日志命中生成的白名单可见。
- 故障模板：支持多对象组、多条件、AND/OR、创建、编辑、删除、启停、导入、导出。
- 故障诊断：手动触发后能返回匹配模板、未匹配条件、证据和建议。

必须检查的风险：

- `k8s_inspector.db`、`root-test.db`、`subpath-test.db` 不得进入提交。
- `frontend/tsconfig.tsbuildinfo` 是否属于本地构建产物；如是，不得进入提交。
- 历史 review 章节里过期问题不得作为当前阻塞重复派发；当前判断以第 20、21、22 节和最新 worklog 为准。
- 如果发现真实代码问题，先记录 finding，再按最小范围修复；不要在最终验收阶段扩新功能。

worklog 必须写清：

- 执行了哪些命令和结果。
- 手工/测试验收了哪些路径。
- 发现了哪些阻塞问题。
- 是否修复了问题。
- 最终是否建议进入提交/交付。
- 提交前必须排除哪些本地文件。

### 22.2 派发文本

下一条指令发给“整体质量验收”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 22 节，做最终全链路验收。不要新增功能。必须跑 `python3 -m pytest -q backend/tests`、`cd frontend && npm test -- --run`、`cd frontend && npm run build`、`git status --short`。重点验收 namespace/pod 巡检、保存对象分流与导入过滤、关键字/白名单、故障模板、故障诊断。确认本地数据库和构建产物不会进入提交。完成后写 worklog，并给出是否建议进入提交/交付的结论。

## 23. 第十轮 Review 结论与最终收口指令

Review 时间：2026-07-12

Review 对象：

- “整体质量验收”第 22 节执行结果。

本轮复核已执行：

- `python3 -m pytest -q backend/tests`：47 passed，1 warning。
- `cd frontend && npm test -- --run`：7 files passed，19 tests passed。
- `cd frontend && npm run build`：构建成功。
- `git status --short`：仍存在本地运行产物和构建产物。

### 23.1 本轮结论

代码质量门禁通过：

- 后端全量测试通过。
- 前端全量测试通过。
- 前端生产构建通过。
- 关键功能路径从代码和测试覆盖看已经具备：namespace/pod 巡检、保存对象分流与导入过滤、关键字/白名单、故障模板、故障诊断。

但当前还不能建议进入提交/交付，因为第 22 节要求的最终验收收口没有完成：

- 没有发现新的“整体质量验收”worklog。
- 工作区仍存在本地数据库文件。
- 工作区仍存在 `frontend/tsconfig.tsbuildinfo` 构建产物。

### 23.2 必须处理的阻塞项

阻塞 1：缺少最终验收 worklog。

- 期望新增类似 `worklog/codex-final-quality-gate-2026-07-12.md` 的文件。
- worklog 必须写清执行命令、结果、验收路径、发现问题、是否建议提交/交付、提交前排除文件。

阻塞 2：本地运行产物不能进入提交。

当前检测到：

- `k8s_inspector.db`
- `root-test.db`
- `subpath-test.db`
- `backend/k8s_inspector.db`
- `backend/root-test.db`
- `backend/subpath-test.db`
- `frontend/tsconfig.tsbuildinfo`

要求：

- 提交前这些文件不得被 `git add`。
- 如果项目已有 `.gitignore`，确认这些模式已覆盖。
- 如果 `.gitignore` 未覆盖，最小补充忽略规则。
- 如果需要删除本地生成物，只能删除确认是测试/运行生成的产物，不要删除业务文件。

### 23.3 派发给“整体质量验收”的返工指令

让“整体质量验收”只做最终收口，不要改业务功能。

必须完成：

- 新增最终验收 worklog。
- 在 worklog 中记录本轮已经通过的命令结果：
- `python3 -m pytest -q backend/tests`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`
- `git status --short`
- 核对 `.gitignore` 是否覆盖 `.db`、`*.sqlite`、`frontend/tsconfig.tsbuildinfo`。
- 如未覆盖，补最小忽略规则。
- 明确列出提交前禁止加入的本地产物。
- 给出最终建议：是否可以进入提交/交付。

边界：

- 不改后端业务逻辑。
- 不改前端业务逻辑。
- 不新增功能。
- 不重构。
- 不删除不确定来源的文件。

验收命令：

- `git status --short`
- `git check-ignore k8s_inspector.db root-test.db subpath-test.db backend/k8s_inspector.db backend/root-test.db backend/subpath-test.db frontend/tsconfig.tsbuildinfo`

### 23.4 派发文本

下一条指令发给“整体质量验收”：

> 参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 23 节，只做最终验收收口。不要改业务功能。新增最终验收 worklog，记录后端测试、前端测试、前端构建、git status 的结果；核对 `.gitignore` 是否覆盖本地数据库和 `frontend/tsconfig.tsbuildinfo`，如未覆盖只补最小忽略规则；明确提交前禁止加入的本地产物；最后给出是否可以进入提交/交付的结论。

## 24. 最终 Review 结论

Review 时间：2026-07-12

Review 对象：

- `worklog/codex-final-e2e-acceptance-2026-07-12.md`
- 最终质量门禁
- 提交卫生状态

最终复核结果：

- 最终验收 worklog 已补齐。
- `.gitignore` 已覆盖根目录 `.db` 和 `frontend/*.tsbuildinfo`。
- `git check-ignore` 已确认以下本地产物会被忽略：
- `k8s_inspector.db`
- `root-test.db`
- `subpath-test.db`
- `backend/k8s_inspector.db`
- `backend/root-test.db`
- `backend/subpath-test.db`
- `frontend/tsconfig.tsbuildinfo`
- `frontend/tsconfig.tsbuildinfo` 当前从版本库索引移除，属于预期的构建缓存清理。

最终复跑命令：

- `python3 -m pytest -q backend/tests`：47 passed，1 warning。
- `cd frontend && npm test -- --run`：7 files passed，19 tests passed。
- `cd frontend && npm run build`：构建成功。

最终结论：

- 功能验收通过。
- 契约复核通过。
- 本地产物忽略规则已补齐。
- 可以进入提交/交付流程。

提交前注意：

- 不要提交被忽略的本地数据库文件。
- `frontend/tsconfig.tsbuildinfo` 的删除应作为“移除已跟踪构建缓存”进入提交。
- 提交时应包含业务代码、测试、契约文档、验收 worklog 和 `.gitignore` 变更。
- 不要把未确认来源的本地运行文件强行加入版本库。

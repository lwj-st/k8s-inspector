# Worklog: 最终轻量契约复核

## 时间

- 日期：2026-07-12
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-11-agent-development-instructions.md` 第 20 节，对共享契约做最终轻量复核。

本轮只做：

1. 核对后端 Pydantic schema
2. 核对前端 `api/types.ts`
3. 核对前端 `api/client.ts`
4. 核对保存对象导入/导出契约
5. 核对模板 `targets/target_groups` 兼容
6. 核对诊断 `direction` 枚举

本轮不做：

1. 不扩新功能
2. 不做 UI 重构
3. 不改 matcher 语义
4. 不改后端接口路径

## 本次核对的文件

### 文档

- `docs/superpowers/plans/2026-07-11-api-contract.md`
- `docs/superpowers/plans/2026-07-11-agent-development-instructions.md`

### 后端 schema

- `backend/app/schemas/common.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/diagnosis.py`
- `backend/app/schemas/template.py`
- `backend/app/schemas/saved_target.py`
- `backend/app/schemas/keyword.py`
- `backend/app/schemas/whitelist.py`

### 后端相关接口与测试

- `backend/app/api/routes/saved_targets.py`
- `backend/app/api/routes/templates.py`
- `backend/app/services/saved_target_service.py`
- `backend/tests/test_contract_models.py`
- `backend/tests/test_template_api.py`
- `backend/tests/test_saved_targets_api.py`
- `backend/tests/test_whitelist_api.py`

### 前端

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`

## 核对结果

### 1. 后端 schema 与前端类型

已确认以下共享枚举仍保持收紧：

- `InspectionTarget.type`
- `SavedInspectionTarget.target_type`
- `KeywordHit.severity`
- `TemplateCondition.condition_type`
- `TemplateCondition.operator`
- `DiagnosisResponse.direction`

结论：

- 后端 schema 与前端类型当前一致

### 2. 模板 `targets / target_groups` 兼容

已确认：

- `targets` 仍是主字段
- `target_groups` 仍只用于兼容输入/兼容输出
- 后端模板 schema 仍会把旧结构归一到 `targets`
- 前端 `FaultTemplate.target_groups` 当前也按兼容输出建模

结论：

- 这部分当前一致

### 3. 保存对象导入/导出

已确认：

- 后端导出返回 `SavedInspectionTargetRead`
- 后端导入接收 `SavedInspectionTargetCreate`
- 前端 `api/client.ts` 已覆盖：
  - list
  - create
  - update
  - delete
  - export
  - import
- 前端 `useSavedInspectionTargets.ts` 已按当前 `target_type` 过滤导入内容

结论：

- 保存对象导入/导出链路当前和契约一致

### 4. 前端 API client 覆盖情况

已确认 `api/client.ts` 已覆盖本轮需要关注的关键接口：

- 模板：
  - list
  - create
  - update
  - enable
  - disable
  - delete
  - export
  - import
- 保存对象：
  - list
  - create
  - update
  - delete
  - export
  - import
- 关键字：
  - list
  - create
  - update
  - delete
  - export
  - import
  - enable
  - disable
- 白名单：
  - list
  - create
  - update
  - delete
  - export
  - import
  - enable
  - disable
  - ignore

结论：

- 本轮未发现前端 client 漏掉后端已存在的关键契约接口

## 发现的不一致

本轮没有发现需要改代码的明确共享契约不一致。

也就是说：

- 没有新增 schema 修正
- 没有新增前端类型修正
- 没有新增 `api/client.ts` 修正
- 没有新增测试修正

## 本轮实际修改

本轮只补充了文档状态说明：

- 在总文档第 20 节下新增“当前最终状态说明”
- 明确更早章节中的部分返工描述属于历史 review，不代表当前仓库实时状态

原因：

- 第 20 节明确要求“清理或标注文档中过期的返工描述，避免后续 agent 被旧章节误导”
- 历史 review 不能删除，因此采用新增状态说明的方式处理

## 验证结果

按第 20 节要求已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_template_api.py backend/tests/test_saved_targets_api.py backend/tests/test_whitelist_api.py
```

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果见本轮最终回复。

## 当前结论

第 20 节要求的“最终轻量契约复核”当前通过。

可以进入下一步：

- “整体质量验收”

## 仍需整体质量验收关注的残余风险

本轮没有共享契约不一致，但仍有两类风险不属于本轮处理范围：

1. matcher 业务语义风险
- 本轮按要求没有改 matcher 语义
- 因此 matcher 是否完全符合业务预期，仍应由整体质量验收继续关注

2. 大量并行改动下的集成风险
- 当前工作区仍存在多个任务线的改动
- 虽然本轮核对的契约项一致，但整体工作流仍需要最终全量验收确认

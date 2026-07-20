# Worklog: 切片 11 关键字库与白名单契约复核

## 时间

- 日期：2026-07-19
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-19-template-authoring-slice-10-acceptance-and-next.md` 中给“统一契约与数据模型”的指令，只读复核关键字库与白名单相关前后端契约，确认当前字段是否足够支撑页面体验收口，并明确前端是否可以开始。

## 检查范围

已检查：

1. `frontend/src/api/types.ts`
2. `backend/app/schemas/keyword.py`
3. `backend/app/schemas/whitelist.py`
4. `backend/app/api/routes/keywords.py`
5. `backend/app/api/routes/whitelists.py`
6. `frontend/src/api/client.ts`
7. `frontend/src/features/whitelists/useKeywords.ts`
8. `frontend/src/features/whitelists/useWhitelists.ts`
9. `frontend/src/pages/WhitelistsPage.tsx`
10. 巡检页里“忽略此报错”的调用点

## 复核结论

### 1. 关键字库契约已足够

当前关键字规则核心字段：

1. `id`
2. `keyword`
3. `category`
4. `severity`
5. `description`
6. `enabled`
7. `builtin`

现有能力已覆盖页面体验收口所需：

1. 展示关键字内容
2. 展示严重程度
3. 展示启停状态
4. 区分内置规则与用户规则
5. 支持新增、编辑、删除、启停、导入、导出

结论：

- 不需要新增关键字字段
- 前端可以直接围绕这些字段做摘要化展示和次级操作收纳

### 2. 白名单契约已足够

当前白名单核心字段：

1. `id`
2. `namespace`
3. `label_selector`
4. `pod_name_pattern`
5. `container_name`
6. `keyword`
7. `enabled`
8. `note`
9. `created_at`
10. `updated_at`

现有能力已覆盖页面体验收口所需：

1. 展示忽略生效范围
2. 展示忽略关键字
3. 展示启停状态
4. 展示备注说明
5. 支持新增、编辑、删除、启停、导入、导出

结论：

- 不需要新增白名单字段
- 当前字段已经足够把“忽略了什么、作用在哪”表达清楚

### 3. “忽略此报错”与白名单页契约一致

现有忽略入口使用：

- `POST /api/v1/whitelists/ignore`

请求字段：

1. `namespace`
2. `label_selector`
3. `pod_name_pattern`
4. `container_name`
5. `keyword`
6. `note`

返回：

- `WhitelistRead`

这意味着：

1. 从巡检页点“忽略此报错”生成的规则可以直接被白名单管理页展示
2. `note` 可用于说明来源
3. 白名单页无需额外契约来解释“这条规则是从哪个入口来的”

### 4. 导入导出契约也已具备

当前关键字和白名单都已具备：

1. `list`
2. `create`
3. `update`
4. `delete`
5. `enable`
6. `disable`
7. `export`
8. `import`

结论：

- 切片 11 只需要前端把导入/导出收进弹窗、抽屉或更多操作
- 不需要新增导入导出 API

## 当前未发现的契约缺口

本轮没有发现必须新增的字段，包括但不限于：

1. 关键字命中样例字段
2. 白名单来源枚举字段
3. 白名单作用对象展示专用 summary 字段
4. 关键字/白名单 UI 专用状态字段

如果后续页面想展示“来源”，当前优先应直接复用：

- `note`

而不是先新增后端字段。

## 对切片 11 前端的明确结论

前端可以开始，且可以只改页面体验，不需要等待后端扩字段。

建议前端直接围绕现有字段完成：

1. 关键字库摘要列表
2. 白名单摘要列表
3. 启停状态突出展示
4. 导入/导出弹窗化
5. 编辑表单弹窗化或局部展开
6. 来源说明优先复用 `note`

## 边界提醒

本切片前端重构时不要：

1. 改日志匹配语义
2. 改白名单过滤语义
3. 新增关键字/白名单后端字段
4. 改巡检主流程

## 当前结论

切片 11 在契约层没有阻塞，前端可以直接开始做体验收口。

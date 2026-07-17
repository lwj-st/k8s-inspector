# Worklog: 巡检编排与检查入口 / 保存巡检对象

## 时间

- 日期：2026-07-11
- Agent：Codex

## 任务范围

本次记录包含两部分工作：

1. 《巡检编排与检查入口》
2. 保存巡检对象能力补齐（重点是保存名称空间巡检对象）

本次工作只负责：

- 巡检入口编排
- `namespace / pod / cluster` 巡检分发
- Pod 巡检入口
- 已保存巡检对象的基础 CRUD
- 命名空间巡检页接入真实保存对象接口

本次工作不负责：

- 故障模板录入器 UI
- 巡检对象导入导出
- 已保存巡检对象编辑/更新
- 模板与 saved target 的联动

## 已完成内容

### 1. 巡检编排与检查入口

已补齐后端巡检入口：

- `POST /api/v1/inspections/cluster/run`
- `POST /api/v1/inspections/namespace/run`
- `POST /api/v1/inspections/pod/run`
- `POST /api/v1/inspections/run`
- `GET /api/v1/inspections/cluster/history`
- `GET /api/v1/inspections/namespace/history`
- `GET /api/v1/inspections/pod/history`

已完成内容：

- 新增 `InspectionRunRequest / InspectionRunResponse`
- 新增 `PodInspectionRequest / PodInspectionResponse`
- `inspection_service` 统一负责：
  - 分发巡检目标
  - 保存巡检记录
  - 返回统一巡检结果
- `pod` 巡检支持独立记录历史，不再只能依附于名称空间巡检

### 2. 巡检证据结构补齐

已补齐 `InspectedPod` 的关键字段：

- `node_name`
- `containers`
- `previous_log_summary`
- `related_resources`
- `log_hits`

说明：

- 这些字段是为了让名称空间巡检和 Pod 巡检都能承载更完整的证据
- 后续模板、白名单、前端详情页都可以直接复用

### 3. 保存巡检对象后端能力

已新增“已保存巡检对象”基础链路：

- 模型：
  - `SavedInspectionTarget`
- 接口：
  - `GET /api/v1/inspection-targets`
  - `POST /api/v1/inspection-targets`
  - `DELETE /api/v1/inspection-targets/{id}`

已支持保存字段：

- `name`
- `target_type`
- `namespace`
- `label_selector`
- `pod_name`
- `resource_scope`

当前重点支持：

- 保存名称空间巡检对象
- 后续一键复用 `namespace + label selector`

本轮补充后，已保存巡检对象接口进一步扩展为：

- `GET /api/v1/inspection-targets`
- `POST /api/v1/inspection-targets`
- `PUT /api/v1/inspection-targets/{id}`
- `DELETE /api/v1/inspection-targets/{id}`
- `GET /api/v1/inspection-targets/export`
- `POST /api/v1/inspection-targets/import`

新增能力：

- 更新保存对象
- 导出为 JSON
- 从 JSON 导入

### 5. 批量名称空间巡检入口补齐

已完成：

- `POST /api/v1/inspections/namespaces/run`

本轮补充后的行为约束：

- 支持显式传入多个 `namespaces`
- 支持 `all_namespaces=true` 时对发现结果批量巡检
- `results` 按 namespace name 排序返回，便于前端稳定展示
- 单个 namespace 巡检失败时只影响该 namespace 自己

失败隔离策略：

- `run_namespace_batch_inspection` 对每个 namespace 单独执行
- 如果某个 namespace 的 provider 巡检抛异常：
  - 整个接口仍返回 `200`
  - 该 namespace 在 `results` 中标记为 `health_status=error`
  - 该 namespace 的 `summary.status=error`
  - 其他 namespace 继续正常返回，不受影响

这样前端可以同时拿到：

- 正常 namespace 的巡检结果
- 失败 namespace 的错误占位结果
- 一个稳定排序后的批量结果列表

### 4. 命名空间巡检页接入真实保存对象

前端已不再只依赖写死的演示卡片。

已完成：

- 新增 `useSavedInspectionTargets`
- 页面启动时读取 `GET /inspection-targets`
- 支持在命名空间巡检页输入“保存名称”
- 点击“保存当前范围”后调用真实接口创建保存对象
- 保存后，列表立即刷新，可直接点击“使用 xxx”发起巡检

现在用户已经可以保存：

- 整个名称空间巡检对象
- 带 `label selector` 的名称空间巡检对象

本轮补充后，页面还支持：

- 编辑已有巡检对象
- 刷新并查看导出 JSON
- 粘贴 JSON 导入巡检对象

## 主要文件

### 后端

- `backend/app/api/routes/inspections.py`
- `backend/app/api/routes/saved_targets.py`
- `backend/app/api/router.py`
- `backend/app/models/saved_inspection_target.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/inspection.py`
- `backend/app/schemas/saved_target.py`
- `backend/app/services/inspection_service.py`
- `backend/app/services/saved_target_service.py`
- `backend/app/services/__init__.py`
- `backend/app/providers/base.py`
- `backend/app/providers/mock_provider.py`
- `backend/app/providers/kubernetes_provider.py`
- `backend/tests/test_inspection_api.py`
- `backend/tests/test_saved_targets_api.py`

### 前端

- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/features/inspections/useRunNamespaceInspection.ts`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`

## 验证结果

已执行后端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest backend/tests/test_saved_targets_api.py backend/tests/test_inspection_api.py -v
```

结果：

- `8 passed, 1 warning`

已执行后端保存对象专项测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest backend/tests/test_saved_targets_api.py -v
```

结果：

- `4 passed, 1 warning`

已执行前端页面测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run src/pages/NamespaceInspectionPage.test.tsx
```

结果：

- `1 file passed`
- `2 tests passed`

本轮补充后再次执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run src/pages/NamespaceInspectionPage.test.tsx
```

结果：

- `1 file passed`
- `3 tests passed`

本轮补充后执行后端批量巡检专项测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest backend/tests/test_inspection_api.py -k "namespace_batch" -v
```

覆盖点：

- 指定 namespace 批量巡检
- `all_namespaces=true` 批量巡检
- 单个 namespace 失败隔离，不影响整个接口
- 显式传入乱序 namespace 时，`results` 仍按 name 排序

结果：

- `4 passed`

本轮补充后执行后端巡检接口全量测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector
python3 -m pytest backend/tests/test_inspection_api.py -v
```

结果：

- `11 passed, 1 warning`

## 当前结论

这两块能力目前已达到“可交接、可继续联动”的状态：

1. 巡检入口后端链路已经打通
2. Pod 巡检有独立入口和历史
3. 名称空间巡检对象已经可以真实保存、更新、导入、导出和复用
4. 前端不再完全依赖写死 demo 对象

## 需要其他 agent 协同的事项

### 1. 和《统一契约与数据模型》协同

需要遵守：

- 不要再扩散 `InspectionTarget` 共享字段
- `saved_target_id` 目前仍是预留字段
- 如果后续要让巡检结果真正回填 `saved_target_id`，应先确认契约文档再改

### 2. 和《关键字库与白名单》协同

需要确认：

- 名称空间巡检页现在既承载保存对象，也承载“忽略此报错”
- 如果继续改这个页面，注意不要把保存对象逻辑和白名单逻辑耦死
- 后续若页面进一步拆分，建议将“保存对象”和“日志忽略”拆成独立 hooks

### 3. 和《前端工作台与人性化 UI》协同

这是当前最需要继续推进的一块：

- 已保存巡检对象现在只有新增、读取、使用
- 还缺：
  - 编辑
  - 删除按钮
  - 导入导出
  - 首页展示“最近使用的巡检对象”
- 单 Pod 巡检页也应接入同样的保存对象思路，但当前还没做

### 4. 和《故障模板与匹配引擎》协同

后续建议：

- 模板检查如果要复用已保存巡检对象，不要直接依赖前端页面状态
- 应通过 `saved_target_id` 或明确的模板绑定关系实现
- 当前后端还没有模板绑定 saved target 的模型和接口

## 当前问题与待协商事项

### 1. 保存巡检对象目前只有基础 CRUD

当前缺口：

- 仍无删除按钮 UI
- 仍无批量管理页
- 导入内容当前只支持粘贴 JSON 文本，不支持文件上传

建议归入后续“配置与资产管理”继续做，不要临时塞进巡检编排 service。

### 2. 巡检编排层和 provider 仍有少量职责重叠

现状：

- provider 会组织部分 Pod 证据结构
- inspection service 也会组织统一结果

后续建议：

- 采集层尽量返回稳定原始证据
- 最终 API 结构由编排层统一收口

### 3. 工作区是脏的

当前仓库里有其他 agent 的未提交改动和未跟踪文件。

本次工作没有回滚任何其他改动，也没有清理本地数据库文件。

后续提交前需要总控确认：

- 哪些文件属于本任务
- 哪些文件属于其他并行任务
- 哪些本地数据库文件需要忽略

## 对后续开发的建议

后续如果继续沿这条线开发，建议按这个顺序：

1. 已保存巡检对象补删除按钮和批量管理
2. 首页接入真实“最近使用的巡检对象”
3. 单 Pod 巡检页支持保存为常用对象
4. 模板检查与 saved target 建立正式绑定关系

# K8s Inspector 首版骨架设计

## 1. 目标

基于现有产品文档，实现一套可继续扩展的首版系统骨架，覆盖前端页面框架、后端 API 框架、SQLite 数据模型、规则引擎边界、模拟数据联调能力，以及可配置的访问前缀能力。

本次目标不是直接接入真实 Kubernetes，而是先把系统骨架、接口结构和页面联调闭环搭起来，为后续接入真实采集能力保留稳定边界。

## 2. 范围

本次实现包含以下内容：

- 前端工程：`React + Vite + TypeScript`
- 后端工程：`FastAPI`
- 本地数据库：`SQLite`
- 六类页面骨架与模拟数据联调
- 模板、白名单、巡检记录、排查记录、系统配置的数据模型
- 规则匹配引擎的首版结构
- 可配置 `BASE_PATH`，同时支持根路径和子路径访问

本次明确不包含：

- 真实 Kubernetes 集群采集
- 登录鉴权
- 自动修复或执行集群命令
- 多集群管理
- 异步任务系统

## 3. 总体架构

系统采用前后端分离结构：

- `frontend/`：负责页面展示、表单交互、结果展示、路由管理
- `backend/`：负责 API、规则匹配、模拟数据提供、配置管理、数据库访问
- `docs/`：设计和后续计划文档
- `examples/`：模板与白名单导入导出样例

前后端通过 REST API 通信。首版默认由同一域名下的反向代理统一对外暴露，前端页面和后端 API 共用一个访问前缀。

## 4. 技术选型

### 4.1 前端

- `React`
- `Vite`
- `TypeScript`
- `React Router`

选择理由：

- 从空目录起步更轻量
- 构建与开发体验简单
- 适合先搭页面骨架和联调结构
- 后续切换真实接口时改动小

### 4.2 后端

- `FastAPI`
- `Pydantic`
- `SQLAlchemy`

选择理由：

- 适合快速搭建结构清晰的 API
- 与结构化配置、规则结果、JSON 字段配合较好
- 后续接入 Kubernetes SDK、调度逻辑、大模型调用都比较直接

### 4.3 数据库

- `SQLite`

选择理由：

- 首版轻量
- 易于本地启动和迁移
- 符合单集群、单管理员、低部署成本目标

## 5. 访问方式设计

系统必须支持两种访问形式：

- 根路径访问：`https://xxx/`
- 子路径访问：`https://xxx/inspector/`

为此增加统一配置项 `BASE_PATH`。

规则如下：

- `BASE_PATH` 可为空或 `/`
- 也可配置为 `/inspector` 这类子路径
- 前端路由 `basename` 使用该配置
- 前端静态资源公共路径使用该配置
- 前端请求 API 的基础地址使用该配置
- 后端 API 统一暴露为 `BASE_PATH + /api/v1`

同域名部署方式如下：

- 页面入口：`https://xxx/inspector/`
- API 入口：`https://xxx/inspector/api/v1/...`

这样后续无论部署在根路径还是网关子路径下，都只需要改配置，不需要改代码。

## 6. 页面与接口设计

### 6.1 集群总览 / 自检结果页

页面展示：

- 集群健康状态
- 异常组件卡片
- 最近一次自检时间
- 最近问题摘要

后端接口：

- `GET /api/v1/overview`
- `POST /api/v1/inspections/cluster/run`
- `GET /api/v1/inspections/cluster/history`

### 6.2 命名空间巡检页

页面展示：

- 命名空间输入
- 可选 `label selector`
- 巡检结果列表
- 对象详情抽屉或详情面板

后端接口：

- `POST /api/v1/inspections/namespace/run`
- `GET /api/v1/inspections/namespace/history`

返回结果至少包含：

- `pods`
- `services`
- `ingresses`
- `tls_secrets`
- `daemonsets`

其中 `pod` 结果需带：

- `status`
- `restarts`
- `events`
- `describe_summary`
- `log_summary`
- `resource_usage`

### 6.3 定点排查页

页面展示：

- 排查方向
- 命名空间
- 对象范围
- 命中模板
- 证据
- 建议
- 命令
- 风险提示

后端接口：

- `POST /api/v1/diagnoses/run`
- `GET /api/v1/diagnoses/history`

返回状态区分：

- `matched`
- `unmatched`
- `llm_supplemented`

### 6.4 故障模板管理页

页面能力：

- 新增
- 编辑
- 删除
- 启用
- 停用
- 导入
- 导出

后端接口：

- `GET /api/v1/templates`
- `POST /api/v1/templates`
- `PUT /api/v1/templates/{id}`
- `DELETE /api/v1/templates/{id}`
- `POST /api/v1/templates/{id}/enable`
- `POST /api/v1/templates/import`
- `GET /api/v1/templates/export`

### 6.5 白名单管理页

页面能力：

- 管理 `namespace + label selector + keyword`
- 查看命中范围
- 启停规则

后端接口：

- `GET /api/v1/whitelists`
- `POST /api/v1/whitelists`
- `PUT /api/v1/whitelists/{id}`
- `DELETE /api/v1/whitelists/{id}`

### 6.6 系统配置页

页面能力：

- 配置 LLM 参数
- 配置默认巡检策略
- 查看系统状态

后端接口：

- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `GET /api/v1/system/status`

## 7. 后端目录设计

建议结构如下：

```text
backend/
  app/
    api/
    core/
    db/
    engine/
    models/
    providers/
    schemas/
    services/
    main.py
```

职责划分：

- `api/`：路由入口
- `core/`：配置、常量、启动逻辑
- `db/`：数据库连接、初始化
- `engine/`：规则匹配
- `models/`：ORM 模型
- `providers/`：数据采集提供者，首版使用 `mock`
- `schemas/`：请求响应结构
- `services/`：业务服务

## 8. 前端目录设计

建议结构如下：

```text
frontend/
  src/
    api/
    app/
    components/
    features/
    hooks/
    layouts/
    pages/
    routes/
    types/
    utils/
```

职责划分：

- `api/`：请求封装
- `app/`：应用启动、全局配置
- `components/`：通用组件
- `features/`：按业务域组织的页面逻辑
- `layouts/`：布局容器
- `pages/`：页面入口
- `routes/`：路由定义
- `types/`：接口类型

## 9. 数据模型设计

### 9.1 `fault_templates`

保存故障模板，字段包括：

- 模板名称
- 适用场景
- 对象范围
- 命名空间范围
- `label_selector`
- 匹配条件 JSON
- 多 Pod 联合规则 JSON
- 故障原因
- 处理建议
- 处理命令
- 风险提示
- 启用状态
- 创建时间
- 更新时间

### 9.2 `whitelists`

保存日志白名单，字段包括：

- `namespace`
- `label_selector`
- `keyword`
- `enabled`
- 备注
- 创建时间
- 更新时间

### 9.3 `inspection_records`

保存集群自检和命名空间巡检记录，字段包括：

- 巡检类型
- 请求参数 JSON
- 巡检结果 JSON
- 摘要状态
- 执行时间

### 9.4 `diagnosis_records`

保存定点排查记录，字段包括：

- 排查方向
- 请求参数 JSON
- 命中模板 JSON
- 证据摘要 JSON
- 分析结果状态
- LLM 补充结果 JSON
- 执行时间

### 9.5 `system_settings`

保存系统配置，字段包括：

- `base_path`
- LLM 开关
- 模型地址
- `api_key`
- 默认巡检策略 JSON
- 更新时间

说明：

- 首版为了开发效率，复杂结构优先存 `JSON`
- 暂不做过度拆表
- 后续如需统计查询增强，再逐步结构化

## 10. 规则引擎设计

首版规则引擎只做结构化匹配，不做复杂 DSL 解释器。

模板匹配条件采用结构化 JSON，支持以下维度：

- `pod_status`
- `restart_count`
- `event_keyword`
- `log_keyword`
- `resource_threshold`
- `node_status`
- `related_object_status`

多 Pod 联合规则也采用结构化 JSON，支持：

- 对象组
- `namespace`
- `label_selector`
- `min_hit_count`
- 逻辑关系 `AND/OR`

输出内容包括：

- 是否命中
- 命中的条件项
- 关联证据
- 故障原因
- 处理建议
- 处理命令
- 风险提示

当未命中规则但开启 LLM 配置时，追加补充分析结果，但不能替代模板结论，也不能触发任何集群动作。

## 11. Mock 数据策略

首版默认使用 `mock provider`，用于打通页面与后端联调。

内置至少三类样例：

- 基座组件异常场景
- 命名空间 Pod 异常场景
- 定点排查的命中、未命中、LLM 补充场景

要求：

- 样例字段结构尽量接近最终真实接口
- 前端直接按最终响应结构消费
- 后续接入真实 Kubernetes 时，只替换 `provider` 和部分服务层，不改前端页面结构

## 12. 真实采集的预留边界

虽然首版不接真实 Kubernetes，但必须预留采集边界。

建议定义统一 Provider 接口，后续至少可扩展：

- `MockInspectionProvider`
- `KubernetesInspectionProvider`

服务层只依赖抽象接口，不直接依赖具体实现。这样后续从模拟数据切到真实集群时，不需要重写业务路由和页面逻辑。

## 13. 测试策略

首版骨架建议至少覆盖：

- 后端 API 基本可用测试
- 规则引擎基础匹配测试
- 模板与白名单 CRUD 测试
- 前端关键页面渲染与基础交互测试
- `BASE_PATH` 路由和请求前缀测试

重点验证：

- 根路径模式能访问
- 子路径模式能访问
- 页面和 API 在同域名前缀下工作正常

## 14. 实施顺序建议

建议按以下顺序实现：

1. 初始化前后端工程和基础目录
2. 完成后端配置、数据库、基础路由
3. 完成前端路由、布局和导航
4. 实现模板、白名单、配置的 CRUD 接口
5. 实现 mock 巡检与定点排查接口
6. 实现六类页面与接口联调
7. 补充基础测试与示例导入文件

## 15. 风险与约束

- 最大风险仍然是模板设计质量，而不是骨架本身
- 首版大量使用 JSON 字段，后续如果要做复杂统计，需要再结构化
- `BASE_PATH` 如果处理不统一，前后端联调会出现静态资源和路由问题，因此必须从一开始统一设计
- Mock 数据必须尽量贴近真实结构，否则后续切真实采集时会返工

## 16. 结论

本设计采用 `React(Vite) + FastAPI + SQLite` 的轻量前后端分离方案，优先实现完整系统骨架和模拟数据联调，并将“同域名访问 + 可配置子路径前缀”作为首版固定能力。这样可以在较低复杂度下快速得到一个可演示、可扩展、可继续接入真实 Kubernetes 的系统基础。

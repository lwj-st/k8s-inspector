# Worklog: 关键字库与白名单

## 时间

- 日期：2026-07-11
- Agent：Codex

## 任务范围

完成《关键字库与白名单》能力，并补齐前后端联动。

本任务只负责：

1. 关键字库的录入、查询、导入、导出
2. 白名单规则的录入、查询、导入、导出
3. 巡检结果中的日志命中 `log_hits`
4. 在巡检页面里对指定日志命中执行“忽略此报错”，并落成白名单

本任务不负责：

1. 巡检采集链路本身
2. 故障模板设计与匹配编排
3. saved targets 的完整产品闭环

## 已完成内容

### 1. 后端：关键字库

- 新增关键字规则模型与 schema
- 提供关键字管理接口：
  - `GET /api/v1/keywords`
  - `POST /api/v1/keywords`
  - `PUT /api/v1/keywords/{id}`
  - `DELETE /api/v1/keywords/{id}`
  - `GET /api/v1/keywords/export`
  - `POST /api/v1/keywords/import`
- 初始化阶段会补默认关键字

### 2. 后端：白名单

- 白名单规则支持更细粒度字段：
  - `namespace`
  - `label_selector`
  - `pod_name_pattern`
  - `container_name`
  - `keyword`
  - `note`
- 提供白名单接口：
  - `GET /api/v1/whitelists`
  - `POST /api/v1/whitelists`
  - `POST /api/v1/whitelists/ignore`
  - `POST /api/v1/whitelists/{id}/enable`
  - `POST /api/v1/whitelists/{id}/disable`
  - `GET /api/v1/whitelists/export`
  - `POST /api/v1/whitelists/import`
- `pod_name_pattern` 语义已收口为 shell 风格通配符
  - 例如：`demo-api-*`

### 3. 后端：巡检结果联动

- 名称空间巡检和 Pod 巡检结果可返回 `log_hits`
- 每条 `log_hit` 会标识：
  - 命中的关键字
  - 容器名
  - 对应日志行
  - 是否已被白名单忽略
- 关键字 `severity` 已复用冻结枚举：
  - `info`
  - `warning`
  - `error`
  - `critical`
- 模板日志条件已统一消费 `log_hits`
- `whitelisted=true` 的日志命中不会再被模板当作有效异常

### 4. 前端：关键字库与白名单页面

- `WhitelistsPage` 已改为真实管理页，不再是占位展示
- 页面支持：
  - 新增关键字
  - 查看关键字列表
  - 启用关键字
  - 停用关键字
  - 新增白名单
  - 查看白名单列表
  - 启用白名单
  - 停用白名单
- 页面文案已按“先定义异常关键字，再把已知噪音忽略”为主线整理
- 严重级别输入已改为固定选项，不再允许前端随意输入非法值

### 5. 前端：巡检页忽略报错

- `NamespaceInspectionPage` 中“忽略此报错”已接真实接口
- 点击后会调用 `POST /api/v1/whitelists/ignore`
- 忽略成功后，当前页面状态会立刻更新
- 下次巡检同类命中会自动按白名单处理
- `PodInspectionPage` 已改为：
  - 直连 `POST /api/v1/inspections/pod/run`
  - 使用真实 `log_hits`
  - “忽略此报错”直接落白名单接口

## 主要文件

### 后端

- `backend/app/models/keyword_rule.py`
- `backend/app/models/whitelist.py`
- `backend/app/engine/matcher.py`
- `backend/app/schemas/keyword.py`
- `backend/app/schemas/whitelist.py`
- `backend/app/services/keyword_service.py`
- `backend/app/services/whitelist_service.py`
- `backend/app/services/inspection_service.py`
- `backend/app/services/diagnosis_service.py`
- `backend/app/api/routes/keywords.py`
- `backend/app/api/routes/whitelists.py`
- `backend/app/db/init_db.py`
- `backend/tests/test_matcher.py`
- `backend/tests/test_whitelist_api.py`

### 前端

- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/features/inspections/useRunPodInspection.ts`
- `frontend/src/features/whitelists/useKeywords.ts`
- `frontend/src/features/whitelists/useWhitelists.ts`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.test.tsx`
- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/pages/WhitelistsPage.test.tsx`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.test.tsx`

## 验证结果

已执行后端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/backend
python3 -m pytest -q
```

结果：

- `40 passed, 1 warning`

已执行前端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `7 files passed`
- `12 tests passed`

已执行前端构建：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- build 成功

## 边界说明

1. 关键字库负责“系统认为什么算异常”
2. 白名单负责“哪些异常先忽略”
3. 巡检服务负责把日志扫描结果产出成 `log_hits`
4. 前端页面只负责配置和展示，不承载匹配规则引擎
5. 故障模板能力应单独消费巡检结果与 `log_hits`，不要把模板逻辑写回关键字库或白名单模块

## 给后续 agent 的交接建议

1. 如果继续做故障模板，请直接复用 `log_hits` 和白名单状态，不要重复实现日志关键字扫描
2. 如果继续做 saved targets，请不要改动关键字库与白名单的数据结构，避免耦合
3. 如果继续优化 UI，优先增强表单可用性、批量导入导出提示、命中详情展示，不要改接口语义

## 需要协商的点

1. `PodInspectionPage` 已接真实 Pod 巡检接口和忽略接口
- 但命名空间巡检页仍保留内置 demo 快捷对象
- 这属于“前端工作台与人性化 UI”任务后续继续清理的范围

2. 模板引擎现在已经消费 `log_hits`
- 这解决了白名单误命中问题
- 但诊断结果里的 `condition type/operator` 输出枚举兜底，仍应由“故障模板与匹配引擎”任务继续收口

## 2026-07-12 继续开发记录

### 本次补齐内容

1. 白名单页前端补齐剩余管理能力
- 关键词支持：
  - 编辑
  - 删除
  - 导出
  - 导入
- 白名单支持：
  - 编辑
  - 删除
  - 导出
  - 导入

2. 前端 API client 已补齐对应接口封装
- `updateKeyword`
- `deleteKeyword`
- `exportKeywords`
- `importKeywords`
- `updateWhitelist`
- `deleteWhitelist`
- `exportWhitelists`
- `importWhitelists`

3. Hook 已补齐列表状态更新能力
- 关键词 hook 支持本地列表同步：
  - update
  - remove
  - exportAll
  - importAll
- 白名单 hook 支持本地列表同步：
  - update
  - remove
  - exportAll
  - importAll

4. 页面交互方式
- 编辑使用当前表单回填，不额外开弹窗
- 导出直接显示 JSON 文本，方便复制到其他环境
- 导入使用 JSON 文本框，便于 agent 或人工粘贴配置

### 本次主要文件

- `frontend/src/api/client.ts`
- `frontend/src/features/whitelists/useKeywords.ts`
- `frontend/src/features/whitelists/useWhitelists.ts`
- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/pages/WhitelistsPage.test.tsx`

### 本次验证

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run src/pages/WhitelistsPage.test.tsx
```

结果：

- `3 passed`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test -- --run
```

结果：

- `7 files passed`
- `14 tests passed`

已执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- build 成功

## 当前结论

《关键字库与白名单》任务已完成，可继续交给其他 agent 做：

1. saved targets
2. 故障模板录入与匹配
3. 巡检工作台整体 UI 优化

# Worklog: 前端工作台与人性化 UI

## 时间

- 日期：2026-07-12
- Agent：Codex

## 任务范围

完成《前端工作台与人性化 UI》这一条任务当前阶段的前端实现与收尾验证。

本任务主要负责：

1. 把前端从演示页整理成排障工作台
2. 补齐名称空间巡检、单 Pod 巡检、模板检查、关键字库与白名单的可用入口
3. 让前端围绕真实巡检动作展示异常状态、describe、日志命中和忽略动作
4. 优化页面文案、入口组织和操作路径，减少重复输入

本任务不负责：

1. 冻结后端契约
2. 实现 Kubernetes 采集细节
3. 实现模板引擎内部匹配语义
4. 清理其他 agent 的后端改动

## 已完成内容

### 1. 工作台导航和入口整理

- `AppLayout` 已整理为中文工作台导航：
  - 工作台
  - 名称空间巡检
  - 单 Pod 巡检
  - 模板检查
  - 故障模板
  - 白名单
  - 系统配置
- `OverviewPage` 首页入口已改成真实排障场景
- “巡检单个 Pod”入口已改为直达 `/inspections/pod`

### 2. 名称空间巡检页可用化

- `NamespaceInspectionPage` 已支持：
  - 运行整个名称空间巡检
  - 基于名称空间 + label selector 巡检
  - 展示异常 Pod、事件、describe、日志命中
  - 对日志命中执行“忽略此报错”
- “忽略此报错”已接真实白名单接口，不再只是本地假动作
- 已加入保存巡检对象能力：
  - 保存当前范围
  - 更新已保存对象
  - 导出巡检对象
  - 导入巡检对象
- 当前页面仍保留少量内置快捷对象，作为过渡入口

### 3. 单 Pod 巡检入口独立化

- 新增 `PodInspectionPage`
- 路由已接入 `/inspections/pod`
- 页面目标是单独输入名称空间和 Pod 名称后直接巡检
- 当前前端已围绕单 Pod 结果展示：
  - Pod 状态
  - 事件
  - describe 摘要
  - 日志命中
  - 忽略此报错

### 4. 模板检查页重组

- `DiagnosisPage` 已从“手填 namespace/scope 的演示入口”整理为“按已录入模板直接检查”
- 诊断结果已按命中模板卡片展示
- 每个命中结果会展示：
  - 模板名
  - 原因
  - 建议
  - 命中条件
  - 未命中条件
- 页面表达更接近排障场景，而不是接口原始返回

### 5. 关键字库与白名单页可操作化

- `WhitelistsPage` 已从只读列表改成可操作页面
- 页面已支持：
  - 新增关键字
  - 查看关键字列表
  - 启用/停用关键字
  - 新增白名单
  - 查看白名单列表
  - 启用/停用白名单
- 页面文案已整理成产品语义：
  - 标题：`关键字库与白名单`
  - 说明：`先定义系统判异常的关键字，再把已知噪音就地忽略成白名单`
- 内置关键字会展示“系统内置”标识
- 关键字严重级别已改为固定选项，避免前端输入非法值

### 6. 状态展示与样式整理

- `StatusBadge` 已补强状态映射
- `styles.css` 已统一成工作台风格
- 页面信息层次更偏“排障操作台”，不再是单纯说明文案堆叠

### 7. 测试补充

- 已补或更新前端测试：
  - `frontend/src/app/App.test.tsx`
  - `frontend/src/routes/basePath.test.tsx`
  - `frontend/src/pages/NamespaceInspectionPage.test.tsx`
  - `frontend/src/pages/PodInspectionPage.test.tsx`
  - `frontend/src/pages/DiagnosisPage.test.tsx`
  - `frontend/src/pages/TemplatesPage.test.tsx`
  - `frontend/src/pages/WhitelistsPage.test.tsx`

## 主要文件

- `frontend/src/layouts/AppLayout.tsx`
- `frontend/src/routes/index.tsx`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/NamespaceInspectionPage.tsx`
- `frontend/src/pages/PodInspectionPage.tsx`
- `frontend/src/pages/DiagnosisPage.tsx`
- `frontend/src/pages/WhitelistsPage.tsx`
- `frontend/src/styles.css`
- `frontend/src/components/StatusBadge.tsx`
- `frontend/src/features/inspections/useSavedInspectionTargets.ts`
- `frontend/src/features/inspections/useRunPodInspection.ts`
- `frontend/src/features/whitelists/useKeywords.ts`
- `frontend/src/features/whitelists/useWhitelists.ts`
- `frontend/src/features/diagnosis/useRunDiagnosis.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`

## 当前验证结果

已执行前端测试：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm test
```

结果：

- `7 passed`
- `13 tests passed`

已执行前端构建：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend
npm run build
```

结果：

- build 成功

## 边界说明

1. 前端工作台负责把已有巡检、模板、白名单能力组织成用户能操作的界面
2. 前端不自行发明新的业务语义，必须跟随后端契约
3. 前端可以做“展示重组”和“交互收敛”，但不能补写后端缺失规则
4. 巡检对象保存、白名单忽略、模板检查都必须通过真实接口落地
5. 页面中的默认演示数据应逐步清理，但不能阻塞当前联调

## 需要协商的点

1. 名称空间巡检页当前仍保留内置 `demo` 快捷对象
- 这些入口有助于测试和演示
- 但不适合最终生产体验
- 建议由“前端工作台与人性化 UI”后续阶段或总控决定何时移除

2. 单 Pod 巡检页是否已经完全切到专用后端接口，需要和“巡检编排与检查入口”任务再次对齐
- 当前前端已为专用 Pod 巡检入口建页并补测试
- 但最终接口契约仍应以后端收口结果为准

3. 保存巡检对象的导入/导出、更新、删除边界，需要和“巡检编排与检查入口”任务继续确认
- 当前前端已接入保存、更新、导入、导出
- 删除入口这次没有继续补，避免和其他 agent 的后端实现冲突

4. 模板页目前更偏“检查入口”和“结果展示”
- 真正友好的模板录入编辑器还没做完
- 这一部分必须依赖“故障模板与匹配引擎”先稳定条件语义和 operator

5. 关键字库与白名单页当前已支持新增和启停
- 编辑、删除、导入、导出 UI 还可以继续补
- 但前提是和“关键字库与白名单”任务确认最终接口集合已经稳定

## 给后续 agent 的交接建议

1. 如果继续做前端，请优先清理 demo 默认值和内置快捷对象，把首页最近使用对象接到真实 saved targets
2. 如果继续做模板页面，请先确认 `condition_type`、`operator`、`joint_rule` 的最终契约，再做条件块编辑器
3. 如果继续做白名单页面，请补编辑、删除、导入、导出，但不要私自扩字段
4. 如果继续做 Pod 巡检页，请先和后端任务确认专用接口响应结构已经冻结
5. 如果继续做整体体验，请优先减少说明性文字，改成真实控件、空状态、错误提示和操作反馈

## 当前结论

《前端工作台与人性化 UI》这一条任务目前已经完成到“可用工作台”阶段：

1. 主要入口已成型
2. 核心排障路径已可操作
3. 测试与构建当前通过

但它还不是最终验收态，后续仍建议继续推进：

1. 去掉 demo 痕迹
2. 完整 saved targets 闭环
3. 模板录入编辑器
4. 白名单高级管理能力

# 2026-07-20 全局状态文案与页面细节收口（切片 12）工作记录

## 范围

参考：

1. [2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/docs/superpowers/plans/2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md)

本轮只做前端显示层状态文案映射，不改后端契约。

未修改：

1. API response。
2. 巡检健康判断。
3. 模板 matcher。
4. 后端状态枚举。

## 已完成内容

### 1. `StatusBadge` 中文文案映射

文件：

1. [StatusBadge.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/components/StatusBadge.tsx)

完成点：

1. 常见系统状态改为中文显示：
   - `enabled` -> `启用`
   - `disabled` -> `停用`
   - `loading` -> `加载中`
   - `info` -> `信息`
   - `unknown` -> `未知`
   - `healthy` -> `健康`
   - `running` -> `运行中`
   - `ready` -> `就绪`
   - `succeeded` -> `已完成`
   - `completed` -> `已完成`
   - `warning` -> `告警`
   - `error` -> `异常`
   - `failed` -> `失败`
   - `degraded` -> `降级`
   - `critical` -> `严重`
2. `CrashLoopBackOff`、`ImagePullBackOff` 等 Kubernetes 原生诊断状态保持原文。
3. 颜色判断逻辑保持不变，只改显示文案。

### 2. 状态徽标组件测试

文件：

1. [StatusBadge.test.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/components/StatusBadge.test.tsx)

覆盖点：

1. 常见状态映射为中文文案。
2. Kubernetes 原生异常状态保留原文。
3. `status-good / status-warn / status-neutral / status-bad` 颜色类不回退。

### 3. 受影响页面测试断言同步

文件：

1. [TemplatesPage.test.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/pages/TemplatesPage.test.tsx)
2. [WhitelistsPage.test.tsx](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/frontend/src/pages/WhitelistsPage.test.tsx)

完成点：

1. 把英文状态断言改为中文。
2. 避免和操作按钮同名冲突，改成在对应卡片内检查状态徽标。

## 验收记录

已通过：

1. `cd frontend && npm test -- --run`
2. `cd frontend && npm run build`
3. `git status --short`

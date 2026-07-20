# Worklog: 切片 12 状态文案契约复核

## 时间

- 日期：2026-07-20
- Agent：Codex

## 本次目标

参考 `docs/superpowers/plans/2026-07-20-keyword-whitelist-slice-11-acceptance-and-next.md` 中给“统一契约与数据模型”的指令，只读复核切片 12 的 `StatusBadge` 中文文案映射是否污染了 API 类型，确认没有要求后端返回中文状态，也没有改变健康状态枚举和严重级别枚举。

## 检查范围

已检查：

1. `frontend/src/components/StatusBadge.tsx`
2. `frontend/src/components/StatusBadge.test.tsx`
3. `frontend/src/api/types.ts`
4. `worklog/codex-status-copy-slice-12-frontend-2026-07-20.md`
5. 受 `StatusBadge` 影响的典型页面调用点

## 复核结论

### 1. `StatusBadge` 只是显示层映射

当前 `StatusBadge` 做的是：

1. 接收原始 `status: string`
2. 在组件内部把常见状态映射成中文文案
3. 未命中的状态保持原文

例如：

1. `enabled -> 启用`
2. `disabled -> 停用`
3. `healthy -> 健康`
4. `warning -> 告警`
5. `critical -> 严重`
6. `CrashLoopBackOff -> CrashLoopBackOff`

结论：

- 这是纯显示层转换
- 没有把中文文案回写进 API 数据结构

### 2. `frontend/src/api/types.ts` 未被污染

当前前端类型仍保持原始英文技术值：

1. `KeywordHitSeverity = "info" | "warning" | "error" | "critical"`
2. 健康状态相关字段仍是后端返回的原始字符串
3. 没有新增中文状态联合类型
4. 没有把 `enabled/disabled/healthy/...` 替换成中文枚举

结论：

- 前端类型仍然忠实反映后端输出
- `StatusBadge` 没有倒逼 API 类型改成中文

### 3. 后端契约无需改动

本轮没有要求后端：

1. 返回中文状态
2. 新增显示文案字段
3. 修改健康状态字段取值
4. 修改严重级别字段取值

结论：

- 切片 12 不需要任何后端契约调整

### 4. 健康判断和严重级别语义未变化

本轮只改文案展示，没有改变：

1. 巡检健康判断
2. 模板 matcher
3. 白名单过滤
4. 关键字严重级别枚举
5. Kubernetes 原生异常状态保留原文的策略

结论：

- 语义层不变，只有显示层更像中文产品

## 是否需要改代码

不需要。

本轮契约复核没有发现必须修改 `frontend/src/api/types.ts` 或任何后端 schema 的地方。

## 当前结论

切片 12 没有产生契约层问题，`StatusBadge` 的中文状态文案映射是安全的纯前端显示改动，不需要后端配合，也没有污染 API 类型。

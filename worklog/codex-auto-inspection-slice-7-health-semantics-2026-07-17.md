# 切片七后端健康语义记录

## 统一规则

- Pod `Running`、`healthy`、`Succeeded`、`Completed` 视为正常状态。
- 容器 `running` 且无 reason 正常。
- 容器 `terminated / Completed` 且退出码为 0 或未提供时正常。
- waiting 异常 reason、terminated 非 Completed、非零退出码仍视为异常。

## 实现

- 新增内部 `pod_health` helper，provider 和 batch summary 共用。
- 修正 Kubernetes provider 的 namespace 发现和 namespace 巡检健康状态。
- 修正 Kubernetes provider 的单 Pod 巡检和 overview 健康状态判断。
- 删除只允许 Job owner 的旧 Succeeded 终态判断，统一复用 `is_abnormal_pod()`。
- 保留 Completed Pod 的 describe、event、日志命中和关联对象证据。
- 未修改 API 字段和异常分类枚举。

## 验证

- 后端重点回归：38 passed
- 后端全量：85 passed
- 依赖警告：1 个 Starlette/httpx 弃用警告
- 前端全量：47 passed
- 前端 build：通过

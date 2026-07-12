# Worklog: 修单 Pod 巡检，直接读单 Pod

## 时间

- 日期：2026-07-11
- Agent：Codex

## 目标

把单 Pod 巡检从“先跑整个 namespace 巡检再筛一个 Pod”改成“直接读取单个 Pod”。

## 问题定位

修复前：

- `backend/app/providers/mock_provider.py`
- `backend/app/providers/kubernetes_provider.py`

里的 `run_pod_inspection` 都在调用 `run_namespace_inspection(namespace, None)`，再从结果里筛 `pod_name`。

这不符合单 Pod 巡检目标，也会带来：

- 不必要的全 namespace 读取
- 更高延迟
- 逻辑职责不清

## 本次修改

### 1. Kubernetes provider

修改文件：

- `backend/app/providers/kubernetes_provider.py`

变更：

- `run_pod_inspection` 改为直接调用 `read_namespaced_pod`
- 再按该 Pod 补充：
  - `describe_summary`
  - `log_summary`
  - `previous_log_summary`
  - `events`
  - `containers`
  - `related_resources`
- 不再依赖 `run_namespace_inspection`

### 2. Mock provider

修改文件：

- `backend/app/providers/mock_provider.py`

变更：

- `run_pod_inspection` 改为直接构造单 Pod 结果
- 不再依赖 `run_namespace_inspection`

### 3. 测试补充

修改文件：

- `backend/tests/test_inspection_api.py`
- `backend/tests/test_kubernetes_provider.py`

新增验证：

- `mock provider` 的 `run_pod_inspection` 不允许再调用 `run_namespace_inspection`
- `kubernetes provider` 的 `run_pod_inspection` 不允许再调用 `run_namespace_inspection`

## 验证结果

针对本次修复执行：

```bash
cd /Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/backend
python3 -m pytest -q tests/test_inspection_api.py tests/test_kubernetes_provider.py
```

结果：

- `10 passed`

## 说明

本次“单 Pod 直接读取”功能已经完成。

另外，执行全量后端测试时，仓库里还存在与本次修复无关的失败，主要在：

- `template`
- `saved_targets`

这些属于其他任务线的现存问题，不是本次单 Pod 修复引入的问题。

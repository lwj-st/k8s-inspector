# 自动巡检切片三二次 Review 结论与返工指令

## 1. 验收结论

切片三仍暂不通过。

本轮已修复：

1. batch summary 已从本次巡检结果推导五类异常分类。
2. 后端测试已覆盖 `pod_status`、`container_status`、`event`、`log_keyword`、`related_object`。
3. 异常分类输出顺序稳定：`pod_status`、`container_status`、`event`、`log_keyword`、`related_object`。

阻断问题：

1. `backend/app/services/inspection_service.py` 会把关联对象异常推导为 `related_object`。
2. 但 `backend/app/providers/kubernetes_provider.py` 的 namespace `health_status` 仍只看 Pod 状态。
3. 真实集群中如果 ingress 为 `unknown` 或 daemonset 为 `degraded`，但 Pod 都正常，就会出现：
   - `summary.abnormal_categories = ["related_object"]`
   - `summary.status = "healthy"`
   - `health_status = "healthy"`
4. 这会让 UI 同时展示“healthy 状态”和“关联对象异常”，用户无法判断该 namespace 是否真的异常。

相关位置：

1. `backend/app/services/inspection_service.py`：`_derive_namespace_abnormal_categories()` 已包含 `related_object`。
2. `backend/app/providers/kubernetes_provider.py`：`run_namespace_inspection()` 只用 `pod_results` 决定 `health_status`。
3. 当前测试 `test_run_namespace_batch_inspection_derives_related_object_from_namespace_objects` 手动把 provider 返回的 `health_status` 设置成 `warning`，没有覆盖真实 provider 的状态推导。

## 2. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 修正 Kubernetes provider 的 namespace 健康状态推导。

目标文件：

1. `backend/app/providers/kubernetes_provider.py`
2. `backend/tests/test_kubernetes_provider.py`

必须实现：

1. `health_status` 不能只看 Pod。
2. 以下任一对象异常时，namespace `health_status` 必须为 `warning`：
   - Pod 状态非 `Running` / `healthy`
   - ingress `status` 非 `healthy`
   - daemonset `status` 非 `healthy`
   - service `status` 非 `healthy`
   - tls secret `status` 非 `healthy`
3. 当前 provider 中 ingress `unknown` 应视为 warning。
4. 当前 provider 中 daemonset `degraded` 应视为 warning。

禁止事项：

1. 不改前端。
2. 不改 batch summary UI。
3. 不新增日志详情。
4. 不接入白名单。
5. 不接入故障模板匹配。

必须补测试：

1. Pod 全部 Running，但 ingress 为 `unknown` 时，namespace `health_status` 为 `warning`。
2. Pod 全部 Running，但 daemonset 为 `degraded` 时，namespace `health_status` 为 `warning`。
3. Pod 和关联对象都 healthy 时，namespace `health_status` 为 `healthy`。

验证命令：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py
python3 -m pytest -q backend/tests/test_inspection_api.py
python3 -m pytest -q backend/tests
```

## 3. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 在 K8s provider 修正后补一条 batch API 保护性测试。

目标文件：

1. `backend/tests/test_inspection_api.py`

必须补测试：

1. provider 返回 `health_status=warning` 且只有 namespace 级关联对象异常时，batch result 必须同时满足：
   - `summary.status = "warning"`
   - `health_status = "warning"`
   - `summary.abnormal_categories = ["related_object"]`

禁止事项：

1. 不重复实现 provider 健康状态逻辑。
2. 不改前端。
3. 不新增功能入口。

验证命令：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py
python3 -m pytest -q backend/tests
```

## 4. 给“前端工作台与人性化 UI”的指令

前端本轮不需要开发。

后端修复后只做回归验证：

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 5. 当前已跑验证

本次 review 已跑：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py backend/tests/test_kubernetes_provider.py backend/tests/test_contract_models.py
# 34 passed, 1 warning

python3 -m pytest -q backend/tests
# 63 passed, 1 warning

cd frontend && npm test -- --run
# 31 passed

cd frontend && npm run build
# passed
```

测试通过不代表验收通过。当前缺的是真实 provider 健康状态和异常分类的一致性。


# 自动巡检切片三 Review 结论与返工指令

## 1. 验收结论

切片三“名称空间巡检异常摘要增强”暂不通过，原因是后端异常分类推导未完整覆盖契约和开发指令要求。

已通过部分：

1. 前端自动巡检页可以展示批量巡检顶部统计。
2. 前端自动巡检页可以按 `error`、`warning`、`healthy` 排序展示结果。
3. 前端自动巡检页可以把异常分类映射为中文标签。
4. 批量巡检 summary 的 `pod_count`、`abnormal_pod_count` 已从本次巡检结果生成，不再只依赖 discovery 旧摘要。
5. 单个 namespace 巡检失败仍保持局部失败，不影响其他 namespace。

未通过部分：

1. `backend/app/services/inspection_service.py` 当前只从本次巡检结果推导了 `pod_status` 和 `log_keyword`。
2. `container_status`、`event`、`related_object` 没有在 batch summary 中从本次巡检证据推导出来。
3. 后端测试没有覆盖 `container_status`、`event`、`related_object` 三类异常分类的 batch summary 输出。

验证结果：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py backend/tests/test_discovery_api.py backend/tests/test_kubernetes_provider.py backend/tests/test_contract_models.py
# 31 passed, 1 warning

python3 -m pytest -q backend/tests
# 60 passed, 1 warning

cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
# 11 passed

cd frontend && npm test -- --run
# 31 passed

cd frontend && npm run build
# passed
```

测试通过不代表切片三通过。当前测试覆盖不足，遗漏了三类异常分类。

## 2. 给“K8s 采集与证据抽取”的指令

让“K8s 采集与证据抽取” agent 检查单 namespace 巡检结果是否已经稳定提供以下证据字段：

1. Pod 状态：`pods[].status`。
2. 容器状态：`pods[].containers[].state`、`pods[].containers[].reason`、`pods[].containers[].restart_count`。
3. 事件：`pods[].events`。
4. 日志关键字：`pods[].log_hits`。
5. 关联对象：`pods[].related_resources`，以及 namespace 级别的 `services`、`ingresses`、`daemonsets`、`tls_secrets`。

如果字段已经存在，不要改 provider。

只有在字段缺失时，才做最小补齐：

1. Kubernetes provider 的 Pod 结果必须保留 container state/reason/restart_count。
2. Kubernetes provider 的 Pod 结果必须保留 event 摘要。
3. Kubernetes provider 的 Pod 结果必须保留 related_resources 状态。
4. 不返回完整日志原文。
5. 不新增详情接口。
6. 不实现白名单、模板匹配、导入导出。

完成后在 worklog 中写清楚：

1. 哪些证据字段已经存在。
2. 是否修改了 provider。
3. 如果未修改 provider，说明为什么现有字段足够。

## 3. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 修正 batch summary 的异常分类推导。

目标文件优先看：

1. `backend/app/services/inspection_service.py`
2. `backend/tests/test_inspection_api.py`
3. `backend/tests/test_contract_models.py`

必须实现：

1. `pod_status`：任一 Pod 的 `status` 不是 `Running` 或 `healthy` 时出现。
2. `container_status`：任一 container 的状态不是 `running` 或存在异常 `reason` 时出现。典型 reason 包括但不限于 `CrashLoopBackOff`、`ImagePullBackOff`、`ErrImagePull`、`OOMKilled`、`Error`。
3. `event`：任一 Pod 存在 event 时出现。后续可以再细分 Warning event，本切片先按已有 event 摘要量化。
4. `log_keyword`：任一 Pod 存在 `log_hits` 时出现。
5. `related_object`：任一关联对象状态不是 `healthy` 时出现。检查范围包括 `pods[].related_resources`，以及 namespace 巡检结果中的 `services`、`ingresses`、`daemonsets`、`tls_secrets`。

实现边界：

1. 只改 summary 推导和必要测试。
2. 不改前端 UI。
3. 不新增 Pod 详情抽屉。
4. 不新增日志详情。
5. 不接入白名单。
6. 不接入故障模板匹配。

测试必须覆盖：

1. 正常 namespace 的 `abnormal_categories` 为空。
2. Pod 状态异常输出 `pod_status`。
3. 容器状态异常输出 `container_status`。
4. Pod event 非空输出 `event`。
5. 日志命中输出 `log_keyword`。
6. 关联对象异常输出 `related_object`。
7. 多类异常同时存在时，输出稳定顺序：`pod_status`、`container_status`、`event`、`log_keyword`、`related_object`。

建议新增或改造测试：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py
python3 -m pytest -q backend/tests/test_contract_models.py
python3 -m pytest -q backend/tests
```

## 4. 给“前端工作台与人性化 UI”的指令

前端本轮不需要返工，除非后端修正后契约字段发生变化。

如果后端只按既有 `AbnormalCategory` 契约返回：

1. 不要改自动巡检页布局。
2. 不要新增详情抽屉。
3. 不要新增日志原文。
4. 不要新增导入导出。
5. 只需要在后端完成后重新跑前端测试和 build。

验证命令：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 5. 推荐执行顺序

1. 先让“K8s 采集与证据抽取”确认现有证据字段是否足够，不足才补 provider。
2. 再让“巡检编排与检查入口”补齐 batch summary 异常分类推导和后端测试。
3. 最后让“前端工作台与人性化 UI”只做回归验证，不主动改 UI。

不要并行修改同一文件：

1. `backend/app/services/inspection_service.py` 只给“巡检编排与检查入口”改。
2. provider 相关文件只给“K8s 采集与证据抽取”改。
3. 前端文件只在后端契约变化时给“前端工作台与人性化 UI”改。


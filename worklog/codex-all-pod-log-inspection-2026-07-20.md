# 2026-07-20 所有 Pod 日志巡检修正记录

## 背景

用户明确要求：

1. 无论 Pod 状态如何，都需要直接检查日志。
2. 日志中匹配系统关键字后，需要提示异常。
3. 误报可以人工忽略进入白名单。

原实现边界：

1. Kubernetes provider 只在异常状态、非 Running、CrashLoopBackOff、Error、OOMKilled 等情况下读取当前日志摘要。
2. Running Pod 如果日志中已有错误关键字，可能不会被检查出来。

## 本次修正

文件：

1. `backend/app/providers/kubernetes_provider.py`
2. `backend/tests/test_kubernetes_provider.py`
3. `backend/app/services/inspection_service.py`
4. `backend/app/services/diagnosis_service.py`
5. `backend/tests/test_inspection_api.py`
6. `backend/tests/test_diagnosis_api.py`

修正内容：

1. `_pod_issue_summary()` 改为只要 Pod 有容器，就尝试读取当前日志摘要。
2. 不再用 Pod phase 或 waiting reason 限制当前日志读取。
3. 每个 Pod 的每个容器都会读取当前日志摘要，不再只读第一个容器。
4. 每个容器继续保留 `tail_lines=20`，并只取前 5 行作为摘要，避免响应体过大。
5. Pod 级 `log_summary` 会聚合各容器摘要，并用 `[container_name]` 分段展示。
6. 内部新增 `container_log_summaries` 用于逐容器关键字匹配。
7. `inspection_service` 和 `diagnosis_service` 会按容器分别调用关键字库匹配，`KeywordHit.container_name` 保留真实命中容器。
8. 模板匹配也能消费非第一个容器的日志命中。
9. previous log 读取逻辑不变，仍只在 Pod 有重启时读取。
10. 白名单逻辑不变，仍按 namespace、label selector、pod、container、keyword 判断是否忽略。

## 验证

已新增/更新测试：

1. `test_run_pod_inspection_reads_logs_for_every_container_even_when_pod_is_running`
2. `test_run_namespace_inspection_matches_keywords_for_every_container`
3. `test_run_diagnosis_matches_log_keyword_from_non_first_container`

验证点：

1. Running Pod 也会调用 `read_namespaced_pod_log()`。
2. 同一 Pod 的多个容器都会调用 `read_namespaced_pod_log()`。
3. 每个容器日志摘要会进入内部 `container_log_summaries`。
4. 聚合日志摘要会进入 `pod.log_summary`。
5. 日志摘要仍限制为每个容器前 5 行。
6. 名称空间巡检会按容器分别匹配关键字。
7. 故障模板匹配能命中非第一个容器的日志关键字。

已执行：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_diagnosis_api.py backend/tests/test_matcher.py
python3 -m pytest -q backend/tests
```

结果：

1. 相关后端测试：51 passed。
2. `backend/tests`：90 passed。
3. 仅有既有 Starlette/httpx deprecation warning。

## 当前结论

后端已满足“无论 Pod 状态如何，都读取每个 Pod 的每个容器当前日志并参与关键字匹配”的基础要求。

注意：

1. 当前仍是日志摘要检查，不是完整日志浏览器。
2. 当前每个容器读取 `tail_lines=20`，并保留前 5 行摘要用于展示和关键字匹配。

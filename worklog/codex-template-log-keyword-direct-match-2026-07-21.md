# 2026-07-21 故障模板日志关键字直匹配修正记录

## 背景

用户反馈故障模板配置了：

`Cannot connect to redis://default`

实际 Pod 日志中存在：

`Cannot connect to redis://default:**@dragonfly-0...`

但系统诊断结果显示未命中。

## 根因

原诊断链路中，模板 `log_keyword` 主要消费系统关键字库生成的 `log_hits`。

这会导致一个不符合用户习惯的问题：

1. 用户在故障模板里录入了专属日志片段。
2. 但该片段如果没有单独录入系统关键字库，就不会生成对应 `log_hits`。
3. 模板匹配时只看到系统关键字命中结果，因此会误判为“缺少日志关键字”。

另外，K8s 采集层之前只保留每个容器前 5 行日志摘要用于匹配，长日志容易漏掉后面的错误行。

## 修正内容

文件：

1. `backend/app/core/config.py`
2. `backend/app/providers/kubernetes_provider.py`
3. `backend/app/services/keyword_service.py`
4. `backend/app/services/diagnosis_service.py`
5. `backend/tests/test_kubernetes_provider.py`
6. `backend/tests/test_diagnosis_api.py`

实现：

1. 新增配置 `K8S_LOG_TAIL_LINES`，默认 `200`，用于控制每个容器读取多少行当前日志。
2. 新增配置 `K8S_LOG_SUMMARY_LINES`，默认 `5`，用于控制页面摘要展示多少行。
3. Provider 内部保留每个容器完整 tail 日志参与匹配。
4. `log_summary` 仍只展示每个容器前 5 行摘要，避免页面过长。
5. 诊断服务会从模板 `log_keyword` 条件中提取 `expected_value`。
6. 模板日志关键字会作为本次诊断的显式关键字直接扫描每个容器日志，不再要求用户重复录入系统关键字库。
7. 显式模板关键字命中仍会检查白名单，白名单维度保持 `namespace + label selector + pod + container + keyword`。

## 验证

新增测试：

1. `test_run_diagnosis_matches_template_log_keyword_without_keyword_rule`

验证点：

1. 模板配置 `Cannot connect to redis://default`。
2. 容器日志存在 `Cannot connect to redis://default:**@...`。
3. 该关键字未预置在系统关键字库中。
4. 诊断结果仍应命中该故障模板。

已执行：

```bash
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_diagnosis_api.py backend/tests/test_matcher.py backend/tests/test_whitelist_api.py
python3 -m pytest -q backend/tests
```

结果：

1. 相关测试：41 passed。
2. 后端全量测试：92 passed。
3. 仅有既有 Starlette/httpx deprecation warning。

# 自动巡检切片五 Review 结论与返工指令

## 1. 验收结论

切片五“日志关键字命中忽略与白名单闭环”暂不通过。

已完成部分：

1. 前端证据抽屉中日志关键字命中旁已有“忽略此命中”按钮。
2. 已白名单命中显示“已忽略”，按钮禁用。
3. 点击忽略后会展示确认区域，不是静默提交。
4. 确认区域展示 namespace、Label Selector、Pod、容器、关键字。
5. 前端会调用 `/api/v1/whitelists/ignore`。
6. 成功后当前抽屉内该命中会显示为“已忽略”。
7. 失败时抽屉不关闭，并展示错误信息。
8. 契约文档已说明一键忽略默认字段和范围。

阻断问题：

1. 后端 batch summary 的 `log_keyword` 分类仍然只判断 `pod.log_hits` 是否非空。
2. 当前实现没有排除 `whitelisted=true` 的日志命中。
3. 如果某 namespace 只有已白名单的日志命中，batch summary 仍会包含 `log_keyword`，用户仍会看到已忽略误报。
4. 缺少后端测试覆盖“全部日志命中都 whitelisted 时，batch summary 不含 `log_keyword`”。
5. 缺少后端测试覆盖“仍存在未白名单命中时，batch summary 保留 `log_keyword`”。

相关代码位置：

1. `backend/app/services/inspection_service.py`
2. 当前 `_derive_namespace_abnormal_categories()` 中仍是 `if any(pod.get("log_hits") for pod in pods): categories.append("log_keyword")`

验证结果：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
# 17 passed

cd frontend && npm test -- --run
# 37 passed

cd frontend && npm run build
# passed

python3 -m pytest -q backend/tests/test_whitelist_api.py backend/tests/test_inspection_api.py
# 25 passed, 1 warning

python3 -m pytest -q backend/tests
# 67 passed, 1 warning
```

测试通过不代表切片五通过。当前缺口在后端编排层，没有被现有测试覆盖。

## 2. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 返工 batch summary 的 `log_keyword` 推导。

目标文件：

1. `backend/app/services/inspection_service.py`
2. `backend/tests/test_inspection_api.py`

必须实现：

1. `summary.abnormal_categories` 中的 `log_keyword` 只能由未白名单日志命中触发。
2. 如果一个 namespace 内所有 `pod.log_hits` 都是 `whitelisted=true`，则不添加 `log_keyword`。
3. 如果同时存在已白名单命中和未白名单命中，则仍添加 `log_keyword`。
4. 不改变 `pod.log_hits` 本身，前端仍需要看到已忽略命中并展示“已忽略”。

建议实现方式：

```python
def _has_effective_log_hit(pods: list[dict]) -> bool:
    return any(
        not hit.get("whitelisted")
        for pod in pods
        for hit in pod.get("log_hits", [])
    )
```

然后由 `_derive_namespace_abnormal_categories()` 使用该函数。

必须补测试：

1. `pod.log_hits=[{"keyword": "...", "whitelisted": True}]` 时，summary 不含 `log_keyword`。
2. `pod.log_hits=[{"keyword": "...", "whitelisted": True}, {"keyword": "...", "whitelisted": False}]` 时，summary 包含 `log_keyword`。
3. 已白名单命中仍保留在 namespace 详情结果中，不被服务层删除。

验证命令：

```bash
python3 -m pytest -q backend/tests/test_inspection_api.py
python3 -m pytest -q backend/tests
```

禁止事项：

1. 不改白名单 CRUD 接口。
2. 不改前端。
3. 不做模板匹配。
4. 不删除 `pod.log_hits` 中的已白名单命中。

## 3. 给“关键字库与白名单”的指令

让“关键字库与白名单” agent 补足或确认白名单闭环测试。

目标文件：

1. `backend/tests/test_whitelist_api.py`
2. `backend/app/services/whitelist_service.py`
3. `backend/app/services/keyword_service.py`

必须确认：

1. `/api/v1/whitelists/ignore` 创建的规则包含：
   - namespace
   - label_selector
   - pod_name_pattern
   - container_name
   - keyword
   - enabled=true
   - note
2. 下一次 namespace 巡检中，对应 `KeywordHit.whitelisted=true`。
3. `container_name` 不匹配时不能误命中白名单。
4. 禁用白名单后，对应命中恢复为 `whitelisted=false`。

如果现有测试已经覆盖，worklog 中明确列出对应测试名。

禁止事项：

1. 不做 UI。
2. 不做 batch summary 逻辑，那个归“巡检编排与检查入口”。
3. 不改模板匹配。

## 4. 给“前端工作台与人性化 UI”的指令

前端本轮不需要返工。

当前前端已满足本切片 UI 验收点：

1. “忽略此命中”按钮。
2. 确认区域。
3. 正确 payload。
4. 成功后已忽略状态。
5. 失败提示。
6. 已白名单按钮禁用。

只在后端返工完成后做回归：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 5. 给“统一契约与数据模型”的指令

本轮不需要开发。

现有契约足够，问题不在字段缺失，而在 batch summary 消费白名单状态的规则。

## 6. 给“K8s 采集与证据抽取”的指令

本轮不需要开发。

不要扩展日志采集，不要新增完整日志接口。

## 7. 推荐执行顺序

1. 先让“巡检编排与检查入口”修复 `log_keyword` 分类推导和测试。
2. 同时让“关键字库与白名单”确认已有白名单匹配测试是否完整。
3. 最后只做前端回归，不改 UI。


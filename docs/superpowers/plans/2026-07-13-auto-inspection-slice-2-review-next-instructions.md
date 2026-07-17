# 自动巡检切片二前端验收记录与回修指令

## 1. 验收结论

切片二前端接入基本完成，但不建议直接进入 Pod 详情切片。需要先回修一个重试语义问题。

已通过验证：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
python3 -m pytest -q backend/tests/test_contract_models.py
```

结果：

- `AutoInspectionPage.test.tsx`：8 passed。
- 前端全量测试：28 passed。
- 前端生产构建：通过。
- 后端契约测试：11 passed。

## 2. 已完成内容

已确认完成：

1. “巡检选中”已启用。
2. “巡检全部”已启用。
3. “巡检选中”调用 `runNamespaceBatchInspection({ namespaces: selectedNamespaces, all_namespaces: false })`。
4. “巡检全部”调用 `runNamespaceBatchInspection({ namespaces: [], all_namespaces: true })`。
5. 执行中按钮会 disabled，并显示 `巡检中...`。
6. 批量摘要展示 namespace、health status、Pod 数、异常 Pod 数、异常分类。
7. 单个 namespace `health_status=error` 时只展示局部失败。
8. 全局接口失败时展示 `批量巡检请求失败`。
9. 未发现导入导出、保存巡检对象、Pod 详情抽屉、白名单、模板匹配等越界实现。

## 3. 需要回修的问题

### 3.1 “重试批量巡检”没有记录上次执行类型

位置：

- `frontend/src/pages/AutoInspectionPage.tsx`

当前逻辑：

```tsx
onClick={batchResult?.all_namespaces ? handleRunAll : handleRunSelected}
```

问题：

- 如果“巡检全部”请求整体失败，`batchResult` 仍然是 `null`。
- 此时点击“重试批量巡检”会走 `handleRunSelected`，而不是重试上一次的“巡检全部”。
- 如果用户没有选中 namespace，这个重试行为可能发送错误 payload 或无法按预期重试。

正确行为：

- 页面应记录最近一次批量巡检请求 payload。
- 全局失败后点击“重试批量巡检”，必须使用上一次 payload 原样重试。
- 例如上一次是 `all_namespaces=true`，重试也必须继续发送 `{ namespaces: [], all_namespaces: true }`。
- 例如上一次是选中 `["prod-core"]`，重试也必须继续发送 `{ namespaces: ["prod-core"], all_namespaces: false }`。

## 4. 给“前端工作台与人性化 UI”的回修指令

让“前端工作台与人性化 UI” agent 参考本文档，只修重试语义。

必须完成：

1. 在 `AutoInspectionPage` 中保存最近一次批量巡检 payload。
2. “巡检选中”和“巡检全部”发起前写入该 payload。
3. “重试批量巡检”使用最近一次 payload 重试。
4. 当没有最近一次 payload 时，不显示或禁用重试按钮。
5. 补测试：
   - “巡检全部”失败后点击重试，请求体仍是 `{ namespaces: [], all_namespaces: true }`。
   - “巡检选中”失败后点击重试，请求体仍是之前选中的 namespaces，而不是当前变化后的 selection。

禁止事项：

- 不做 Pod 详情。
- 不做日志、describe、event。
- 不做白名单。
- 不做模板。
- 不做导入导出。
- 不改后端接口。

## 5. 回修后验收命令

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

全部通过后，切片二前端才算通过，可进入下一切片。


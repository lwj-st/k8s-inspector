# 自动巡检切片四复验结论：返工未完成

## 1. 复验结论

切片四仍不通过。

本次复验没有看到上次要求的关键返工落地：

1. `frontend/src/pages/AutoInspectionPage.tsx` 仍然用 `summary.name` 发起证据详情请求。
2. `frontend/src/pages/AutoInspectionPage.tsx` 仍然固定传空 `label_selector`。
3. “查看证据”按钮仍只把 `item.summary` 传给处理函数，没有传完整 batch result。
4. 证据抽屉顶部仍没有展示异常分类。
5. 证据抽屉仍没有展示 namespace 级对象：
   - `services`
   - `ingresses`
   - `daemonsets`
   - `tls_secrets`
6. 前端测试仍没有覆盖 `detail_target.namespace` 与 `detail_target.label_selector`。
7. 前端测试仍没有覆盖“Pod 全部正常但 Ingress/DaemonSet 异常时，抽屉能显示异常对象”。

验证命令虽然通过，但不能作为切片四通过依据：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
# 13 passed

cd frontend && npm test -- --run
# 33 passed

cd frontend && npm run build
# passed

python3 -m pytest -q backend/tests
# 67 passed, 1 warning
```

## 2. 退回给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 继续按以下文件返工，不要只跑现有测试：

```text
docs/superpowers/plans/2026-07-17-auto-inspection-slice-4-review-rework-instructions.md
```

必须改到以下验收点全部满足：

1. “查看证据”按钮处理函数接收完整 batch result。
2. 详情请求使用 `item.detail_target.namespace`。
3. `item.detail_target.label_selector` 有值时必须透传。
4. 抽屉顶部展示异常分类中文标签。
5. 抽屉展示 namespace 级对象摘要：
   - Service
   - Ingress
   - DaemonSet
   - TLS Secret
6. namespace 级对象异常时，即使 Pod 全部正常，也必须在抽屉中清楚显示异常原因。
7. 正常 namespace 级对象弱化或折叠，不要把主视图变成长页面。

必须新增或修改测试：

1. 构造 batch result，其中 `summary.name = "summary-name"`，`detail_target.namespace = "detail-name"`，点击“查看证据”后断言请求体 namespace 是 `"detail-name"`。
2. 构造 `detail_target.label_selector = "app=api"`，断言详情请求体包含 `label_selector: "app=api"`。
3. 构造 `summary.abnormal_categories = ["related_object"]`，断言抽屉顶部展示“关联对象”。
4. 构造 namespace 详情：Pod 全部 Running，但 `ingresses=[{name:"demo", status:"unknown"}]` 或 `daemonsets=[{name:"agent", status:"degraded"}]`，断言抽屉显示 `Ingress/demo：unknown` 或 `DaemonSet/agent：degraded`。
5. 保留 loading、失败、异常 Pod 优先展示测试。

验证命令：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

## 3. 其他模块指令

“统一契约与数据模型”本轮不需要开发。

“巡检编排与检查入口”本轮不需要开发。

“K8s 采集与证据抽取”本轮不需要开发。

当前阻断只在前端切片四返工。


# 自动巡检切片四验收结论与切片五开发指令

## 1. 切片四验收结论

切片四“名称空间巡检结果下钻到 Pod 证据”已通过验收。

已确认完成：

1. “查看证据”按钮使用完整 batch result。
2. 详情请求优先使用 `detail_target.namespace`，不再依赖 `summary.name`。
3. `detail_target.label_selector` 有值时会透传；无值时传 `null`。
4. 证据抽屉顶部展示异常分类中文标签。
5. 证据抽屉展示异常 Pod，并折叠正常 Pod。
6. 证据抽屉展示 Pod 级证据：
   - 状态
   - 节点
   - 重启次数
   - 容器状态/reason
   - event 摘要
   - describe 摘要
   - 日志关键字命中
   - Pod 级关联对象
7. 证据抽屉展示 namespace 级关联对象：
   - Service
   - Ingress
   - DaemonSet
   - TLS Secret
8. Pod 全部正常但 Ingress/DaemonSet 异常时，抽屉能显示真实异常对象。
9. 未引入完整日志、完整 describe、模板匹配、导入导出、保存巡检对象等越界能力。

验证命令：

```bash
cd frontend && npm test -- --run src/pages/AutoInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
python3 -m pytest -q backend/tests
python3 -m pytest -q backend/tests/test_kubernetes_provider.py backend/tests/test_inspection_api.py backend/tests/test_contract_models.py
```

验证结果：

1. 自动巡检页测试：14 passed。
2. 前端全量测试：34 passed。
3. 前端生产构建：通过。
4. 后端全量测试：67 passed，1 warning。
5. 后端重点测试：35 passed，1 warning。

## 2. 切片五目标

切片五只做“日志关键字命中忽略与白名单闭环”。

用户在证据抽屉看到日志关键字命中后，应能把确认的误报加入白名单。加入后，后续巡检不再把同一范围内的同类日志命中当作有效异常。

本切片解决的问题：

1. 用户不用反复看到已确认的误报。
2. 白名单入口从证据场景触发，不再要求用户去单独页面手工拼参数。
3. 忽略操作必须可追踪、可验证、可回滚。

本切片仍然不做：

1. 故障模板匹配。
2. 完整日志原文查看。
3. 完整 describe 原文查看。
4. 自动定时巡检。
5. 导入导出主流程。
6. 保存巡检对象。

## 3. 给“统一契约与数据模型”的指令

让“统一契约与数据模型” agent 先复核现有白名单契约是否足够支持“从日志命中一键忽略”。

优先复用：

1. `KeywordHit`
2. `WhitelistCreate`
3. `WhitelistResponse`
4. `container_name`
5. `namespace`
6. `label_selector`
7. `pod_name_pattern`
8. `keyword`
9. `enabled`
10. `note`

必须明确：

1. 一键忽略的默认白名单范围是什么。
2. 推荐默认范围：`namespace + pod_name_pattern + container_name + keyword`。
3. 如果当前巡检来自 `detail_target.label_selector`，白名单也应带上该 `label_selector`。
4. `pod_name_pattern` 默认可以用当前 Pod 名；后续再做通配规则编辑。
5. `note` 默认写入来源，例如“自动巡检证据抽屉忽略”。

禁止事项：

1. 不新增重复白名单模型。
2. 不把白名单逻辑塞进模板模型。
3. 不新增批量导入导出。

验收标准：

1. 契约文档说明一键忽略生成的白名单字段。
2. 前后端类型一致。
3. 如果现有契约足够，worklog 明确写“无需新增字段”。

## 4. 给“关键字库与白名单”的指令

让“关键字库与白名单” agent 确认后端白名单创建与日志命中过滤闭环。

必须保证：

1. 已存在创建白名单接口可用于前端一键忽略。
2. 创建后下一次 namespace 巡检中，对应 `KeywordHit.whitelisted` 为 `true`，或该命中不再计入有效异常。
3. 白名单匹配至少覆盖：
   - namespace
   - label_selector
   - pod_name_pattern
   - container_name
   - keyword
   - enabled
4. 禁用白名单后，命中应恢复。

禁止事项：

1. 不做 UI。
2. 不做模板匹配。
3. 不做日志采集扩展。
4. 不新增完整日志接口。

验收标准：

1. 后端测试覆盖创建白名单后 namespace 巡检日志命中被标记或过滤。
2. 后端测试覆盖 container_name 匹配。
3. 后端测试覆盖禁用白名单后恢复命中。
4. 后端全量测试通过。

## 5. 给“巡检编排与检查入口”的指令

让“巡检编排与检查入口” agent 只检查巡检结果如何消费白名单状态。

必须确认：

1. namespace 巡检返回的 `pod.log_hits` 能体现白名单状态。
2. batch summary 的 `log_keyword` 分类不应因为只存在已白名单命中而继续报警。
3. 如果既有白名单命中又有未白名单命中，仍应保留 `log_keyword`。

禁止事项：

1. 不改白名单管理接口。
2. 不改前端。
3. 不做模板匹配。

验收标准：

1. 后端测试覆盖“全部日志命中都 whitelisted 时，batch summary 不含 `log_keyword`”。
2. 后端测试覆盖“仍存在未白名单命中时，batch summary 保留 `log_keyword`”。

## 6. 给“前端工作台与人性化 UI”的指令

让“前端工作台与人性化 UI” agent 在证据抽屉里实现误报忽略入口。

交互要求：

1. 只在日志关键字命中旁提供“忽略此命中”。
2. 已白名单命中显示“已忽略”，按钮禁用。
3. 点击“忽略此命中”后弹出确认弹窗或轻量确认区，不要直接静默提交。
4. 确认内容必须让用户看懂将忽略什么：
   - namespace
   - Pod
   - container
   - keyword
   - label selector
5. 成功后刷新当前 namespace 证据，或局部更新该 hit 为已忽略。
6. 失败时展示可读错误，不关闭抽屉。

UI 要求：

1. 不要把白名单表单平铺进主页面。
2. 不要新增大按钮。
3. 忽略入口必须贴近具体日志命中。
4. 文案必须说明“后续匹配相同范围将不再作为异常提示”。

禁止事项：

1. 不做完整白名单管理页重构。
2. 不做导入导出。
3. 不做模板匹配。
4. 不展示完整日志原文。

验收标准：

1. 前端测试覆盖点击“忽略此命中”会带正确字段创建白名单。
2. 前端测试覆盖确认弹窗。
3. 前端测试覆盖已白名单命中按钮禁用。
4. 前端测试覆盖创建失败提示。
5. 前端全量测试和 build 通过。

## 7. 给“K8s 采集与证据抽取”的指令

本切片默认不需要“K8s 采集与证据抽取”开发。

只有当白名单闭环发现缺少 `container_name` 或日志命中来源字段时，才允许最小补齐。

禁止事项：

1. 不扩展完整日志采集。
2. 不改 K8s 对象采集范围。
3. 不做 UI。

## 8. 推荐执行顺序

1. 先让“统一契约与数据模型”确认一键忽略字段契约。
2. 再让“关键字库与白名单”确认后端创建和过滤闭环。
3. 再让“巡检编排与检查入口”确认 batch summary 不被已白名单命中误导。
4. 最后让“前端工作台与人性化 UI”做证据抽屉的一键忽略交互。

并行边界：

1. “统一契约与数据模型”只改文档和类型。
2. “关键字库与白名单”只改白名单服务、接口和测试。
3. “巡检编排与检查入口”只改巡检结果消费规则和测试。
4. “前端工作台与人性化 UI”只改证据抽屉交互和前端测试。
5. “K8s 采集与证据抽取”默认不参与，除非明确缺字段。


# 切片 9：故障模板匹配结果体验增强

## 背景

自动巡检入口已经完成下拉式重构。接下来回到用户最早提出的第二个核心能力：

> 我们会录入故障模板，比如 pod1 有固定日志匹配 + pod2 有固定日志匹配 + 某个 pod 的状态为 fail + ... 常见能量化的错误。之后手动触发检查，系统要挨个检查这些能不能匹配，是不是这个故障。

当前模板匹配已能运行，但结果解释不够像诊断工具：

1. 后端 `summary` 只有“模板名 命中/未命中”，价值低。
2. 未命中模板完整展开，容易淹没真正命中的模板。
3. 条件解释能看到，但没有明确“为什么命中 / 为什么未命中”。
4. 采集失败模板有结果，但前端展示不够突出。

## 总目标

让模板匹配结果更像“故障诊断结果”，而不是原始规则列表。

用户触发模板匹配后，应优先看到：

1. 命中了哪些已知故障。
2. 为什么认为命中。
3. 哪些证据支撑命中。
4. 没命中的模板为什么没命中，但不要默认铺满页面。
5. 哪些模板因为采集失败无法判断。

## 执行顺序

1. 先让 “故障模板与匹配引擎” 做 9A。
2. 9A 完成并通过后，再让 “前端工作台与人性化 UI” 做 9B。
3. “统一契约与数据模型” 只做轻量复核，防止字段膨胀。

不要让 9A 和 9B 同时改 `DiagnosisResultPanel` 或 diagnosis response 结构。

## 9A：让 “故障模板与匹配引擎” agent 处理

### 目标

增强后端 diagnosis/template result 的解释文本，保持现有 API 契约。

### 重点文件

1. `backend/app/services/diagnosis_service.py`
2. `backend/app/engine/matcher.py`
3. `backend/tests/test_diagnosis_api.py`
4. `backend/tests/test_matcher.py`
5. `backend/tests/test_template_api.py`

### 必须实现

#### 1. 优化 `template_match_results[].summary`

当前：

```text
模板名 命中
模板名 未命中
```

需要改为更有解释性的摘要。

命中模板示例：

```text
命中 2/3 个条件：api Pod 状态匹配 CrashLoopBackOff；api 日志命中 connection refused。
```

未命中模板示例：

```text
未命中：缺少 redis 日志关键字 redis timeout；worker 重启次数未达到 >= 3。
```

采集失败模板示例：

```text
无法判断：采集 demo/app=api 失败，错误：Forbidden。
```

#### 2. 保持结构不变

优先只增强以下现有字段：

1. `summary`
2. `reason`
3. `suggestion`
4. `risk_note`
5. `evidence_refs`
6. `matched_conditions`
7. `unmatched_conditions`

除非必须，不新增 response 字段。

#### 3. 条件解释要覆盖现有类型

至少覆盖：

1. `pod_status`
2. `log_keyword`
3. `event_keyword`
4. `restart_count`
5. `related_object_status`

要求：

1. 能带上 `target_ref`。
2. 能带上 operator 和 expected value。
3. 对 `log_keyword` 要说明关键字。
4. 对 `related_object_status` 要说明资源类型和状态。

#### 4. 采集失败不能吞掉模板

单个模板采集失败时：

1. `template_match_results` 中必须保留该模板。
2. `matched=false`。
3. `summary` 明确“无法判断”。
4. `reason` 可以保留错误详情，但不要只把错误塞给前端看。
5. 整次 diagnosis 不能失败。

#### 5. 白名单逻辑不能回退

已白名单日志命中不能让模板命中。

### 禁止事项

1. 不引入 AI 总结。
2. 不改 `TemplateConditionOperator` 枚举。
3. 不把完整 namespace inspection 结果塞进 diagnosis response。
4. 不改前端布局。
5. 不改模板录入页。
6. 不改 Pod 健康判定。

### 测试要求

必须新增/调整：

1. 命中模板返回解释性 `summary`。
2. 未命中模板返回缺失条件解释。
3. 采集失败模板返回“无法判断”摘要。
4. 白名单日志不参与模板命中的回归仍通过。
5. 多 Pod 匹配仍保持“任一 Pod 命中即可”。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_matcher.py backend/tests/test_diagnosis_api.py backend/tests/test_template_api.py
python3 -m pytest -q backend/tests
```

输出 worklog：

```text
worklog/codex-diagnosis-template-result-slice-9a-2026-07-19.md
```

## 9B：让 “前端工作台与人性化 UI” agent 处理

### 前置条件

必须等 9A 完成并通过。

### 目标

优化模板匹配结果展示，让用户先看命中，再按需看未命中。

### 重点文件

1. `frontend/src/features/diagnosis/DiagnosisResultPanel.tsx`
2. `frontend/src/pages/DiagnosisPage.tsx`
3. `frontend/src/pages/DiagnosisPage.test.tsx`
4. `frontend/src/pages/AutoInspectionPage.test.tsx`
5. `frontend/src/pages/NamespaceInspectionPage.test.tsx`
6. `frontend/src/styles.css`

### 必须实现

#### 1. 命中模板优先

展示顺序：

1. 总览：命中几个、未命中几个、无法判断几个。
2. 已命中模板：默认展开。
3. 无法判断模板：默认展示为警告/提示。
4. 未命中模板：默认折叠。

#### 2. 未命中模板不能默认铺满页面

要求：

1. 未命中模板放入 `<details>` 或等价折叠区。
2. 折叠标题说明数量。
3. 用户展开后能看到未命中条件。

#### 3. 证据更像诊断结果

每个命中模板卡片应突出：

1. 故障名称。
2. 命中摘要。
3. 命中条件。
4. 关键证据。
5. 建议处理动作。
6. 风险说明。

#### 4. 采集失败模板要明确

如果 `summary` 包含“无法判断”或没有命中且 evidence 为空但 reason 是采集错误，应作为“无法判断”区展示。

不要把采集失败混入普通未命中。

#### 5. 保持入口不丢

以下入口不能删：

1. 自动巡检页批量摘要的模板匹配入口。
2. 名称空间巡检结果中的模板匹配入口。
3. 独立诊断页面的模板检查入口。

### 禁止事项

1. 不改后端 API。
2. 不改 matcher。
3. 不把未命中模板默认全部展开。
4. 不删除白名单忽略入口。
5. 不改巡检入口 IA。

### 测试要求

必须覆盖：

1. 命中模板默认可见。
2. 未命中模板默认折叠。
3. 展开后能看到未命中条件。
4. 采集失败模板进入“无法判断”区。
5. 自动巡检页和名称空间巡检页模板匹配入口仍可触发。

验收命令：

```bash
cd frontend && npm test -- --run src/pages/DiagnosisPage.test.tsx src/pages/AutoInspectionPage.test.tsx src/pages/NamespaceInspectionPage.test.tsx
cd frontend && npm test -- --run
cd frontend && npm run build
```

输出 worklog：

```text
worklog/codex-diagnosis-template-result-slice-9b-2026-07-19.md
```

## 轻量契约复核

让 “统一契约与数据模型” 在 9A/9B 后复核。

目标：

1. 确认没有无必要新增 response 字段。
2. 确认前端类型仍覆盖后端输出。
3. 确认 `DiagnosisResponse.direction`、`template_match_results` 结构未分裂。

验收命令：

```bash
python3 -m pytest -q backend/tests/test_contract_models.py backend/tests/test_diagnosis_api.py
cd frontend && npm test -- --run src/pages/DiagnosisPage.test.tsx
```

输出 worklog：

```text
worklog/codex-diagnosis-template-result-slice-9-contract-review-2026-07-19.md
```

## 总体验收标准

切片 9 完成后必须满足：

1. 用户一眼能看到命中的故障模板。
2. 命中模板说明为什么命中。
3. 未命中模板不再铺满页面。
4. 采集失败模板不再像普通未命中。
5. 不扩后端契约，除非有明确必要。
6. 后端全量、前端全量和构建通过。

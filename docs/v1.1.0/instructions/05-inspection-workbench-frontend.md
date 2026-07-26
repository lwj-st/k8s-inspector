# Agent 05 指令：v1.1.0 巡检工作台前端

## Agent 名称

`v1.1-inspection-workbench`

## 开工条件

分两个阶段：

1. UX 设计阶段：`v1.1-contract-architecture` 通过后开始。
2. 前端实现阶段：UX 设计稿、平台安全基础通过总调度验收后开始。

## 必读

- `docs/v1.1.0/README.md`
- `docs/v1.1.0/prd.md`
- `docs/v1.1.0/feasibility-review.md`
- `docs/v1.1.0/agent-execution-plan.md`
- `docs/v1.1.0/architecture-contract.md`
- 当前 Overview、AutoInspection、NamespaceInspection、Diagnosis、Settings 页面和相关测试

## 目标

把现有巡检页面升级为问题工作台，让用户优先看到“什么坏了、影响什么、证据是什么、下一步做什么”。

## 允许修改

UX 设计阶段只允许修改：

- `docs/v1.1.0/ux-design.md`
- `worklog/v1.1-inspection-workbench-<实际日期>.md`

实现阶段经总调度批准后允许修改：

- `frontend/src/pages/**`
- `frontend/src/features/**`
- `frontend/src/components/**`
- `frontend/src/api/**`
- `frontend/src/routes/**`
- `frontend/src/layouts/**`
- `frontend/src/styles.css`
- 对应前端测试

## 禁止修改

- `backend/**`
- `deploy/**`
- PRD、契约和其他 Agent 指令
- 与 v1.1.0 无关的前端模块

白名单外文件必须先申请总调度批准。

## UX 设计阶段必须完成

在改代码前提交 `docs/v1.1.0/ux-design.md`，至少包含：

1. 登录和 Session 失效流程。
2. 首页信息层级。
3. 问题列表、筛选、确认和详情流程。
4. 访问配置链路展示。
5. Coverage 的 passed、abnormal、skipped、failed 表达。
6. 定时计划、通用 Webhook 和飞书群机器人通知配置流程。
7. 系统状态和降级状态。
8. loading、empty、error、permission denied、partial success。
9. 桌面端和窄屏布局。
10. 关键操作的确认、成功和失败反馈。
11. 如何避免长页面、重复入口和功能堆叠。

总调度未批准 UX 设计稿前，不得修改前端代码。

## 必须完成

1. 首页问题总览：
   - 开放问题
   - critical/warning
   - 最近恢复
   - 最近巡检
   - 覆盖率
2. 问题列表：
   - 严重程度
   - 状态
   - 名称空间
   - 资源类型
   - 持续时间
   - 筛选和排序
3. 问题详情：
   - 结论
   - 影响
   - 证据链
   - 建议
   - 时间线
4. 访问链路紧凑展示：
   - Ingress
   - Service
   - EndpointSlice
   - Pod
5. 展示 coverage：
   - passed
   - abnormal
   - skipped
   - failed
6. skipped 和 failed 不得使用健康绿色。
7. 定时巡检计划管理。
8. 通用 Webhook 和飞书群机器人通知渠道管理、脱敏状态和连接测试；飞书渠道不要求用户填写消息 JSON。
9. 敏感字段始终显示脱敏值。
10. 保留模板匹配、白名单和日志命中忽略入口。
11. 保留正常 Pod 和正常资源折叠逻辑。
12. 提供 Mock 数据覆盖正常、异常、恢复、跳过和失败状态。
13. 登录、退出、Session 过期和 401/403 处理。
14. 问题确认和确认备注，明确提示“确认不会恢复问题”。
15. 系统状态页面显示数据库、Kubernetes API、调度器、Metrics API、通知和配置校验状态。
16. 日志巡检超过范围时在发起前提示并引导缩小名称空间、标签或 Pod 范围。
17. 在设置区提供必需组件策略管理，清楚区分“自动发现的可选组件”和“缺失即告警的必需组件”。
18. 飞书设置仅展示群机器人 Webhook、可选签名密钥、启停和测试；明确提示“仅发送群告警，不接收消息”。
19. “仅 critical 时提醒所有人”开关默认关闭，并在开启前说明打扰范围。

## 交互边界

1. 日常首页不堆放计划和通知表单。
2. 计划与通知放入设置或次级管理区。
3. 不创建与现有自动巡检功能重复的新页面。
4. 不在前端重新推导后端健康状态。
5. 不显示完整 Webhook 地址和 Secret。
6. 未加载到数据时不能显示“全部正常”。
7. 静态检查只能显示“配置链路正常”，不能显示“访问正常”。
8. 正常信息折叠，异常、影响和下一步操作优先。
9. 后端返回的内部枚举必须映射为易懂中文，同时保留原始状态详情。
10. 筛选条件、分页和当前查看位置在详情关闭后保持。
11. 表单必须提供字段说明、校验错误和安全提示，不能只显示失败代码。

## 验收

至少执行：

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

必须补充直接 UI 断言，覆盖：

- critical 优先
- recovered 与 open 区分
- skipped/failed 展示
- 问题详情证据链
- 计划创建和启停
- Webhook 脱敏
- 飞书群机器人配置、脱敏、测试通知和默认关闭提醒所有人
- 登录、Session 过期和权限错误
- 问题确认不改变健康状态
- 配置链路文案不冒充真实访问结果
- 窄屏布局和键盘可操作性
- v1.0.0 模板和白名单入口保留

## Worklog

输出：

```text
worklog/v1.1-inspection-workbench-<实际日期>.md
```

在 worklog 中说明：

- UX 设计决策
- 页面信息架构
- 真实浏览器验收结果
- loading、empty、error、permission denied、partial success 覆盖
- 最终 `git diff --name-only` 与允许修改清单对比

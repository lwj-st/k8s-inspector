# Cursor Fault Template Output

## Purpose

Use this skill when Cursor or another AI assistant is asked to investigate a Kubernetes incident and produce output that can be directly entered into this repository's K8s Inspector fault template UI.

The output must not be a generic incident summary. It must be a quantifiable, repeatable fault template with object groups, match conditions, reasons, suggestions, commands, and risks.

## Instructions To Give Cursor

Copy the following prompt to Cursor when asking it to investigate a fault and produce a reusable template:

```text
你现在是 K8s 故障模板分析助手。请基于我提供的故障现场、日志、describe、kubectl 输出、服务调用链和业务现象，整理一个可录入到 K8s Inspector 系统的故障模板。

重要目标：
1. 不要只做普通排障总结。
2. 必须输出“可量化、可重复匹配”的故障模板内容。
3. 输出内容要能让我直接在系统的“故障模板”页面录入。
4. 如果证据不足，必须明确写“不能模板化”的原因，不要编造条件。
5. 多个 Pod 匹配同一个 Label Selector 时，只要任意一个 Pod 满足条件，就视为该对象组条件成立。

系统支持的模板字段如下：

一、模板基础信息
- 模板名称 name：中文，能让运维一眼看懂。
- 场景标识 scenario：英文小写、下划线命名，例如 redis_connect_failed。
- 启用 enabled：默认 true。

二、对象组 targets
每个对象组必须包含：
- target_ref：对象组标识，例如 group-1、api、worker、redis。
- namespace：名称空间。
- label_selector：用于定位 Pod，不要用 Pod 名，因为 Pod 会重启变名。
- resource_scope：资源范围，可选值包括 pods、services、ingresses、daemonsets、secrets。

对象组要求：
- 如果涉及多个服务/组件，请拆成多个对象组。
- 每个对象组必须尽量使用稳定 Label Selector。
- 不要用 pod-template-hash、controller-revision-hash 这类不稳定 label。
- 如果不知道 Label Selector，请明确写“需要人工补充 Label Selector”。

三、匹配条件 match_conditions
系统支持这些 condition_type：

1. log_keyword
含义：对象组内任意 Pod 日志包含指定关键字。
字段：
- target_ref
- condition_type: log_keyword
- operator: contains
- expected_value: 日志关键字或完整日志片段

适用场景：
- 连接失败
- redis/mysql/es/kafka 连接异常
- Python Traceback
- 前端运行时报错
- Java exception
- Node.js error

2. pod_status
含义：对象组内 Pod 状态匹配。
operator 可用：
- equals
- in

expected_value 示例：
- "CrashLoopBackOff"
- ["CrashLoopBackOff", "Failed", "ImagePullBackOff"]

3. restart_count
含义：Pod 重启次数满足阈值。
operator 可用：
- gte
- lte
- equals

expected_value 示例：
- 3

4. event_keyword
含义：Pod event 中包含关键字。
operator:
- contains

expected_value 示例：
- "Back-off restarting failed container"
- "FailedMount"
- "Readiness probe failed"

5. related_object_status
含义：关联对象状态异常，例如 Service、Ingress、DaemonSet、TLS Secret。
operator:
- in
- equals

expected_value 使用对象格式：
{
  "resource": "services | ingresses | daemonsets | secrets",
  "object_name": "具体对象名，可为空",
  "match_any": true 或 false,
  "statuses": ["degraded", "unknown", "missing"]
}

四、条件组合
- 默认使用 AND。
- 如果必须满足全部条件，joint_rule.operator = AND。
- 如果多个条件满足任意一个即可，joint_rule.operator = OR。
- 每个条件也可以写 join_operator，默认 AND。

五、原因和建议
必须输出：
- reason：为什么这是这个故障。
- suggestion：建议处理动作，必须可执行。
- command：建议排查命令，尽量给 kubectl 命令。
- risk_note：执行建议动作的风险说明。

请按以下格式输出，不要省略字段：

## 1. 故障模板录入内容

模板名称：
场景标识：
启用：

对象组：
| target_ref | namespace | label_selector | resource_scope | 说明 |
|---|---|---|---|---|

匹配条件：
| target_ref | condition_type | operator | expected_value | join_operator | 说明 |
|---|---|---|---|---|---|

判断原因：
处理建议：
建议命令：
风险说明：

## 2. 可直接导入/对照录入的 JSON

请输出严格 JSON，字段如下：

{
  "name": "",
  "scenario": "",
  "targets": [
    {
      "target_ref": "group-1",
      "namespace": "",
      "label_selector": "",
      "pod_name_pattern": null,
      "resource_scope": ["pods"]
    }
  ],
  "match_conditions": [
    {
      "target_ref": "group-1",
      "condition_type": "log_keyword",
      "operator": "contains",
      "expected_value": "",
      "join_operator": "AND",
      "enabled": true
    }
  ],
  "joint_rule": {
    "operator": "AND"
  },
  "reason": "",
  "suggestion": "",
  "command": "",
  "risk_note": "",
  "enabled": true
}

## 3. 证据说明

请列出每个条件来自哪条证据：
- 日志原文片段
- describe 摘要
- event
- pod 状态
- service/ingress/daemonset/secret 状态

## 4. 不能模板化的信息

请列出哪些内容不能作为模板条件：
- 一次性时间戳
- 临时 Pod 名
- request id / trace id
- IP 如非稳定服务地址
- 随机 hash
- 只出现一次且无法复现的现象

## 5. 需要人工补充的信息

如果缺少以下信息，请明确列出来：
- namespace
- Label Selector
- 关键日志片段
- 对象名
- 状态阈值
- 是否需要 AND 还是 OR
```

## Additional Cursor Requirements

```text
输出时注意：
1. 日志关键字不要太短，避免只写 error、timeout 这种容易误报的词。
2. 优先使用一整段稳定错误片段，例如 Cannot connect to redis://xxx、Error: connect ECONNREFUSED、Back-off restarting failed container。
3. 不要把白名单噪音当成故障模板条件。
4. 不要使用 Pod 名作为匹配条件。
5. 如果一个故障涉及 pod1 日志 + pod2 日志 + 某个服务状态异常，请拆成多个对象组和多个条件。
6. 如果 label 匹配多个 Pod，只要任意一个 Pod 命中该对象组条件即可，不需要精确到某个 Pod。
```

## K8s Inspector Template Contract

The generated JSON must match this system contract:

- `name`: required string.
- `scenario`: required string.
- `targets`: array of object groups.
- `targets[].target_ref`: required stable group id.
- `targets[].namespace`: required namespace.
- `targets[].label_selector`: required when known; prefer stable labels over pod names.
- `targets[].pod_name_pattern`: always `null` unless the product explicitly decides to support pod-name matching again.
- `targets[].resource_scope`: array using `pods`, `services`, `ingresses`, `daemonsets`, `secrets`.
- `match_conditions`: array of quantifiable conditions.
- `match_conditions[].target_ref`: must reference an existing target.
- `condition_type`: one of `pod_status`, `log_keyword`, `event_keyword`, `restart_count`, `related_object_status`.
- `operator`: one of `equals`, `in`, `contains`, `gte`, `lte`.
- `join_operator`: usually `AND`, use `OR` only when the condition is explicitly optional.
- `joint_rule.operator`: `AND` or `OR`.
- `reason`, `suggestion`, `command`, `risk_note`: required for operational usability.

## Quality Bar

Reject or mark as "不能模板化" when:

- The proposed match condition depends on a pod name, pod hash, request id, trace id, timestamp, random IP, or one-off value.
- The log keyword is too broad, such as only `error`, `timeout`, `failed`, or `exception`.
- The output lacks namespace or stable Label Selector and does not clearly ask the user to provide it.
- The root cause is only guessed and not supported by logs, pod status, events, or related object status.

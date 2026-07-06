import { useTemplates } from "../features/templates/useTemplates";
import { StatusBadge } from "../components/StatusBadge";

function describeCondition(condition: Record<string, unknown>) {
  const targetRef = String(condition.target_ref ?? "对象组");
  const type = String(condition.condition_type ?? "unknown");
  const operator = String(condition.operator ?? "equals");
  const expectedValue = String(condition.expected_value ?? "");

  if (type === "log_keyword") {
    return `对象组 ${targetRef} 在日志中包含 ${expectedValue}`;
  }

  if (type === "pod_status") {
    return `对象组 ${targetRef} 的 Pod 状态等于 ${expectedValue}`;
  }

  if (type === "restart_count") {
    return `对象组 ${targetRef} 的重启次数 ${operator} ${expectedValue}`;
  }

  if (type === "event_keyword") {
    return `对象组 ${targetRef} 的事件中包含 ${expectedValue}`;
  }

  return `对象组 ${targetRef} 需要满足 ${type} ${operator} ${expectedValue}`;
}

export function TemplatesPage() {
  const { data, loading } = useTemplates();

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Template Studio</p>
          <h2>故障模板</h2>
        </div>
        <span className="section-tip">先用可视化条件描述，再决定是否下钻到 JSON</span>
      </header>
      <section className="card-grid card-grid-wide">
        <article className="card">
          <div className="section-header">
            <h3>模板录入建议</h3>
          </div>
          <div className="stack-list">
            <div className="stack-item">
              <strong>先定义对象组</strong>
              <p>每个对象组绑定 `namespace + label selector`，后续检查时不再重复输入范围。</p>
            </div>
            <div className="stack-item">
              <strong>再叠加条件块</strong>
              <p>用日志命中、Pod 状态、重启次数、事件关键字拼出自然语言可读规则。</p>
            </div>
            <div className="stack-item">
              <strong>最后补齐建议</strong>
              <p>确保命中后能直接给出原因、处理建议和风险说明。</p>
            </div>
          </div>
        </article>
      </section>
      <div className="card-grid">
        {data.map((item) => (
          <article key={item.id} className="card">
            <div className="card-title">
              <strong>{item.name}</strong>
              <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
            </div>
            <p>
              {item.namespace_scope ?? "未限定名称空间"}
              {item.label_selector ? ` / ${item.label_selector}` : ""}
            </p>
            <p>{item.reason}</p>
            <div className="condition-list">
              {item.match_conditions.map((condition, index) => (
                <div key={`${item.id}-condition-${index}`} className="condition-item">
                  {describeCondition(condition)}
                </div>
              ))}
            </div>
            <p className="inline-note">条件关系：{String(item.joint_rule?.operator ?? "AND")}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

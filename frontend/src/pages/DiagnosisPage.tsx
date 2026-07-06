import { useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";

export function DiagnosisPage() {
  const [namespace, setNamespace] = useState("demo");
  const [scope, setScope] = useState("deployment/demo-api");
  const { data, loading, error, submit } = useRunDiagnosis();

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Template Check</p>
          <h2>故障模板检查</h2>
        </div>
        {data ? <StatusBadge status={data.status} /> : null}
      </header>
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(namespace, scope);
        }}
      >
        <div className="section-header">
          <h3>检查入口</h3>
          <span className="section-tip">当前后端仍使用 namespace + scope 触发，后续会切换到模板预设范围</span>
        </div>
        <label>
          名称空间
          <input value={namespace} onChange={(event) => setNamespace(event.target.value)} />
        </label>
        <label>
          Scope
          <input value={scope} onChange={(event) => setScope(event.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "检查中..." : "运行模板检查"}
        </button>
      </form>
      {error ? <p>排查失败：{error}</p> : null}
      {data ? (
        <div className="panel">
          <div className="card-title">
            <strong>结果状态</strong>
            <StatusBadge status={data.status} />
          </div>
          <p className="inline-note">本次返回来自现有诊断接口，前端已按模板检查语义重组展示。</p>
          {data.matches.map((match) => (
            <article key={match.template_id} className="card">
              <strong>{match.template_name}</strong>
              <p>{match.reason}</p>
              <p>{match.suggestion}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

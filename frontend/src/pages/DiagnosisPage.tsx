import { useState } from "react";

import { StatusBadge } from "../components/StatusBadge";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";

export function DiagnosisPage() {
  const [namespace, setNamespace] = useState("demo");
  const [scope, setScope] = useState("deployment/demo-api");
  const { data, loading, error, submit } = useRunDiagnosis();

  return (
    <section className="page-section">
      <h2>定点排查</h2>
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(namespace, scope);
        }}
      >
        <label>
          Namespace
          <input value={namespace} onChange={(event) => setNamespace(event.target.value)} />
        </label>
        <label>
          Scope
          <input value={scope} onChange={(event) => setScope(event.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "排查中..." : "运行排查"}
        </button>
      </form>
      {error ? <p>排查失败：{error}</p> : null}
      {data ? (
        <div className="panel">
          <div className="card-title">
            <strong>结果状态</strong>
            <StatusBadge status={data.status} />
          </div>
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

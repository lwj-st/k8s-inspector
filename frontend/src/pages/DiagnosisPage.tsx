import { DiagnosisResultPanel } from "../features/diagnosis/DiagnosisResultPanel";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";
import { StatusBadge } from "../components/StatusBadge";

export function DiagnosisPage() {
  const { data, loading, error, submit } = useRunDiagnosis();

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">模板匹配</p>
          <h2>模板检查</h2>
        </div>
        {data ? <StatusBadge status={data.status} /> : null}
      </header>

      <section className="panel panel-muted">
        <div className="section-header">
          <div>
            <h3>按已录入模板直接检查</h3>
            <p className="inline-note">模板里已经绑定名称空间和对象组，这里不再手填范围。</p>
          </div>
        </div>
        <button type="button" onClick={() => void submit()} disabled={loading}>
          {loading ? "检查中..." : "运行模板检查"}
        </button>
      </section>

      <DiagnosisResultPanel data={data} loading={loading} error={error} idleMessage="模板已录入范围，点击后直接运行匹配。" />
    </section>
  );
}

import { PageHeader } from "../components/PageHeader";
import { DiagnosisResultPanel } from "../features/diagnosis/DiagnosisResultPanel";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";

export function DiagnosisPage() {
  const { data, loading, error, submit } = useRunDiagnosis();

  return (
    <section className="page-section">
      <PageHeader title="模板匹配" description="按已录入模板的名称空间和对象组执行检查。" actions={
        <button type="button" className="primary-action" onClick={() => void submit()} disabled={loading}>
          {loading ? "检查中..." : "运行模板检查"}
        </button>
      } />

      <DiagnosisResultPanel data={data} loading={loading} error={error} idleMessage="模板已录入范围，点击后直接运行匹配。" />
    </section>
  );
}

import { useTemplates } from "../features/templates/useTemplates";

export function TemplatesPage() {
  const { data, loading } = useTemplates();

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <h2>故障模板</h2>
      <div className="card-grid">
        {data.map((item) => (
          <article key={item.id} className="card">
            <strong>{item.name}</strong>
            <p>{item.reason}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

import { useWhitelists } from "../features/whitelists/useWhitelists";

export function WhitelistsPage() {
  const { data, loading } = useWhitelists();

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <h2>白名单管理</h2>
      <div className="card-grid">
        {data.map((item) => (
          <article key={item.id} className="card">
            <strong>{item.keyword}</strong>
            <p>{item.namespace}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

import { StatusBadge } from "../components/StatusBadge";
import { useWhitelists } from "../features/whitelists/useWhitelists";

export function WhitelistsPage() {
  const { data, loading } = useWhitelists();

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Whitelist</p>
          <h2>白名单管理</h2>
        </div>
        <span className="section-tip">结果页的“忽略此报错”后续会汇总到这里统一管理</span>
      </header>
      <div className="card-grid">
        {data.map((item) => (
          <article key={item.id} className="card">
            <div className="card-title">
              <strong>{item.keyword}</strong>
              <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
            </div>
            <p>{item.namespace}</p>
            <p>{item.label_selector ?? "未限定 label"}</p>
            {item.note ? <p className="inline-note">{item.note}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

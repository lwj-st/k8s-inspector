import { useSettings } from "../features/settings/useSettings";

export function SettingsPage() {
  const { data, systemStatus, loading } = useSettings();

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <h2>系统配置</h2>
      <div className="panel">
        <label>
          访问前缀
          <input aria-label="访问前缀" value={data?.base_path ?? ""} readOnly />
        </label>
        <label>
          Provider 模式
          <input aria-label="Provider 模式" value={data?.provider_mode ?? systemStatus?.provider_mode ?? "mock"} readOnly />
        </label>
        <label>
          Kubeconfig
          <input aria-label="Kubeconfig" value={data?.kubeconfig_path ?? ""} readOnly />
        </label>
        <label>
          Kube Context
          <input aria-label="Kube Context" value={data?.kube_context ?? systemStatus?.kube_context ?? ""} readOnly />
        </label>
        <label>
          模型提供方
          <input value={data?.llm_provider ?? data?.model ?? ""} readOnly />
        </label>
        <p>系统状态：{systemStatus?.status ?? data?.system_status ?? "unknown"}</p>
        <p>状态说明：{systemStatus?.message ?? "unknown"}</p>
      </div>
    </section>
  );
}

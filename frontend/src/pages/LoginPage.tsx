import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiClientError } from "../api/client";
import { useSession } from "../features/auth/SessionContext";

type LoginLocationState = {
  from?: string;
};

export function LoginPage() {
  const { session, loading: sessionLoading, error: sessionError, login } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const from = (location.state as LoginLocationState | null)?.from ?? "/";

  if (!sessionLoading && session?.authenticated) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 429) {
        setError("尝试次数过多，请稍后再试");
      } else if (reason instanceof ApiClientError && reason.status === 401) {
        setError("用户名或密码不正确");
      } else {
        setError(reason instanceof Error ? reason.message : "登录失败，请重试");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand" aria-hidden="true">K</div>
        <p className="eyebrow">K8s Inspector</p>
        <h1 id="login-title">登录巡检台</h1>
        <p className="inline-note">使用管理员账号查看巡检问题和系统配置。</p>
        {sessionError ? (
          <div className="feedback-banner feedback-warning" role="status">
            登录状态读取失败：{sessionError}
          </div>
        ) : null}
        {error ? (
          <div className="feedback-banner feedback-error" role="alert">
            {error}
          </div>
        ) : null}
        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            用户名
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={submitting}
              autoFocus
            />
          </label>
          <label>
            密码
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
            />
          </label>
          <button type="submit" className="primary-action" disabled={submitting || sessionLoading}>
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}

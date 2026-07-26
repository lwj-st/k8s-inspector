import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useSession } from "../features/auth/SessionContext";

const navItems = [
  { to: "/", label: "问题工作台", end: true },
  { to: "/inspections/status", label: "状态巡检" },
  { to: "/inspections/namespace", label: "日志巡检" },
  { to: "/diagnosis", label: "模板检查" },
  { to: "/templates", label: "故障模板" },
  { to: "/whitelists", label: "关键字与白名单" },
  { to: "/settings", label: "系统设置" },
];

function displayExpiry(value?: string | null) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function AppLayout() {
  const { session, logout } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  async function handleLogout() {
    setLogoutError(null);
    try {
      await logout();
    } catch (reason) {
      setLogoutError(reason instanceof Error ? reason.message : "退出失败");
    }
  }

  return (
    <div className="app-shell">
      <button
        type="button"
        className="mobile-menu-button"
        aria-expanded={menuOpen}
        aria-controls="main-navigation"
        onClick={() => setMenuOpen((current) => !current)}
      >
        {menuOpen ? "关闭菜单" : "打开菜单"}
      </button>
      <aside className={`app-sidebar${menuOpen ? " app-sidebar-open" : ""}`}>
        <div className="brand-block">
          <span className="brand-icon" aria-hidden="true">
            <svg viewBox="0 0 48 48" role="img" focusable="false">
              <path d="M24 4 41.3 14v20L24 44 6.7 34V14L24 4Z" />
              <path d="M24 12v8m0 8v8M13.6 18l6.9 4m7 4 6.9 4m0-12-6.9 4m-7 4-6.9 4" />
              <circle cx="24" cy="24" r="4.5" />
            </svg>
          </span>
          <div>
            <h1>K8s 巡检台</h1>
            <small>可信巡检 · 只读排障</small>
          </div>
        </div>
        <nav id="main-navigation" aria-label="主导航">
          <ul className="nav-list">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="session-summary">
          <strong>{session?.username ?? "管理员"}</strong>
          <small>Session 最长有效至 {displayExpiry(session?.absolute_expires_at)}</small>
          <button type="button" onClick={() => void handleLogout()}>退出登录</button>
          {logoutError ? <span role="alert">{logoutError}</span> : null}
        </div>
      </aside>
      <main className="app-content" id="main-content">
        <Outlet />
      </main>
    </div>
  );
}

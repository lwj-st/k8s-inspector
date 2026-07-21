import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "状态巡检" },
  { to: "/inspections/namespace", label: "日志巡检" },
  { to: "/diagnosis", label: "模板检查" },
  { to: "/templates", label: "故障模板" },
  { to: "/whitelists", label: "关键字库" },
  { to: "/settings", label: "系统配置" },
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <span className="brand-icon" aria-hidden="true">
            <svg viewBox="0 0 48 48" role="img" focusable="false">
              <path d="M24 4 41.3 14v20L24 44 6.7 34V14L24 4Z" />
              <path d="M24 12v8m0 8v8M13.6 18l6.9 4m7 4 6.9 4m0-12-6.9 4m-7 4-6.9 4" />
              <circle cx="24" cy="24" r="4.5" />
            </svg>
          </span>
          <h1>K8s 巡检台</h1>
        </div>
        <nav>
          <ul className="nav-list">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}

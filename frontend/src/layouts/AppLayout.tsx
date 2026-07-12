import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "工作台" },
  { to: "/inspections/namespace", label: "名称空间巡检" },
  { to: "/inspections/pod", label: "单 Pod 巡检" },
  { to: "/diagnosis", label: "模板检查" },
  { to: "/templates", label: "故障模板" },
  { to: "/whitelists", label: "白名单" },
  { to: "/settings", label: "系统配置" },
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <h1>K8s 巡检台</h1>
          <p>名称空间、Pod、模板故障检查</p>
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

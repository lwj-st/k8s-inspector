import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Overview" },
  { to: "/inspections/namespace", label: "Namespace" },
  { to: "/diagnosis", label: "Diagnosis" },
  { to: "/templates", label: "Templates" },
  { to: "/whitelists", label: "Whitelists" },
  { to: "/settings", label: "Settings" },
];

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <h1>K8s Inspector</h1>
        <nav>
          <ul>
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to}>{item.label}</NavLink>
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

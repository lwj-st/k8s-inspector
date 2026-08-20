import { type FormEvent, useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { changePassword } from "../api/client";
import { useSession } from "../features/auth/SessionContext";

const navItems = [
  { to: "/", label: "问题工作台", end: true },
  { to: "/inspections/status", label: "资源巡检" },
  { to: "/inspections/namespace", label: "日志巡检" },
  { to: "/log-recordings", label: "日志记录" },
  { to: "/images", label: "镜像清单" },
  { to: "/diagnosis", label: "模板匹配" },
  { to: "/templates", label: "模板管理" },
  { to: "/whitelists", label: "日志规则" },
  { to: "/settings", label: "系统设置" },
];

const themeStorageKey = "k8s-inspector:theme";
type AppTheme = "light" | "dark";
type ThemePreference = AppTheme | "system";

function readStoredThemePreference(): ThemePreference {
  try {
    const value = window.localStorage?.getItem(themeStorageKey);
    return value === "light" || value === "dark" || value === "system" ? value : "system";
  } catch {
    return "system";
  }
}

function resolveSystemTheme(): AppTheme {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [themePreference, setThemePreference] = useState<ThemePreference>(readStoredThemePreference);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const userMenuRef = useRef<HTMLDivElement | null>(null);
  const username = session?.username ?? "管理员";
  const userInitial = username.trim().slice(0, 1).toUpperCase() || "管";

  useEffect(() => {
    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");

    function applyTheme() {
      document.documentElement.dataset.theme = themePreference === "system" ? resolveSystemTheme() : themePreference;
      document.documentElement.dataset.themePreference = themePreference;
    }

    applyTheme();
    try {
      window.localStorage?.setItem(themeStorageKey, themePreference);
    } catch {
      // 主题切换仍然对当前页面生效。
    }

    if (themePreference !== "system" || !mediaQuery) {
      return;
    }
    mediaQuery.addEventListener?.("change", applyTheme);
    mediaQuery.addListener?.(applyTheme);
    return () => {
      mediaQuery.removeEventListener?.("change", applyTheme);
      mediaQuery.removeListener?.(applyTheme);
    };
  }, [themePreference]);

  useEffect(() => {
    if (!userMenuOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (userMenuRef.current?.contains(event.target as Node)) {
        return;
      }
      setUserMenuOpen(false);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setUserMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [userMenuOpen]);

  async function handleLogout() {
    setLogoutError(null);
    setUserMenuOpen(false);
    try {
      await logout();
    } catch (reason) {
      setLogoutError(reason instanceof Error ? reason.message : "退出失败");
    }
  }

  function closePasswordDialog() {
    setPasswordDialogOpen(false);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setPasswordError(null);
    setPasswordMessage(null);
  }

  async function handlePasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordMessage(null);
    if (newPassword.length < 6) {
      setPasswordError("新密码至少 6 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("两次输入的新密码不一致");
      return;
    }
    setPasswordSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage("密码已更新，其他已登录会话会失效。");
    } catch (reason) {
      setPasswordError(reason instanceof Error ? reason.message : "密码修改失败");
    } finally {
      setPasswordSaving(false);
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
        <div className="session-summary" ref={userMenuRef}>
          <button
            type="button"
            className="user-card-button"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            onClick={() => setUserMenuOpen((current) => !current)}
          >
            <span className="user-avatar" aria-hidden="true">{userInitial}</span>
            <span className="user-card-text">
              <strong>{username}</strong>
              <small>有效至 {displayExpiry(session?.absolute_expires_at) || "--"}</small>
            </span>
          </button>
          {userMenuOpen ? (
            <div className="user-menu" role="menu" aria-label="用户菜单">
              <div className="theme-menu-group" aria-label="主题切换">
                <span>主题切换</span>
                <div className="theme-segment" role="group" aria-label="主题切换">
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={themePreference === "system"}
                    className={themePreference === "system" ? "theme-segment-option theme-segment-option-active" : "theme-segment-option"}
                    onClick={() => setThemePreference("system")}
                  >
                    系统
                  </button>
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={themePreference === "light"}
                    className={themePreference === "light" ? "theme-segment-option theme-segment-option-active" : "theme-segment-option"}
                    onClick={() => setThemePreference("light")}
                  >
                    亮色
                  </button>
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={themePreference === "dark"}
                    className={themePreference === "dark" ? "theme-segment-option theme-segment-option-active" : "theme-segment-option"}
                    onClick={() => setThemePreference("dark")}
                  >
                    暗色
                  </button>
                </div>
              </div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setUserMenuOpen(false);
                  setPasswordDialogOpen(true);
                }}
              >
                更改密码
              </button>
              <button type="button" role="menuitem" onClick={() => void handleLogout()}>
                注销
              </button>
            </div>
          ) : null}
          {logoutError ? <span role="alert">{logoutError}</span> : null}
        </div>
      </aside>
      <main className="app-content" id="main-content">
        <Outlet />
      </main>
      {passwordDialogOpen ? (
        <div className="modal-backdrop" role="presentation">
          <form className="modal-card password-dialog" aria-label="更改密码" onSubmit={handlePasswordChange}>
            <div>
              <p className="eyebrow">账户安全</p>
              <h2>更改密码</h2>
              <p>修改后会保留当前会话，并撤销其他已登录会话。</p>
            </div>
            <label>
              当前密码
              <input
                type="password"
                value={currentPassword}
                autoComplete="current-password"
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            <label>
              新密码
              <input
                type="password"
                value={newPassword}
                autoComplete="new-password"
                minLength={6}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </label>
            <label>
              确认新密码
              <input
                type="password"
                value={confirmPassword}
                autoComplete="new-password"
                minLength={6}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            </label>
            {passwordError ? <p className="form-error" role="alert">{passwordError}</p> : null}
            {passwordMessage ? <p className="form-success" role="status">{passwordMessage}</p> : null}
            <div className="modal-action-row">
              <button className="modal-secondary-button" type="button" onClick={closePasswordDialog} disabled={passwordSaving}>关闭</button>
              <button className="modal-primary-button" type="submit" disabled={passwordSaving}>
                {passwordSaving ? "保存中…" : "保存新密码"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

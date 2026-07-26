import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  configureApiSession,
  getSession,
  login as loginRequest,
  logout as logoutRequest,
} from "../../api/client";
import type { AdminSession } from "../../api/types";

type SessionContextValue = {
  session: AdminSession | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const anonymousSession: AdminSession = { authenticated: false };
const SessionContext = createContext<SessionContextValue | null>(null);

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "无法读取登录状态";
}

export function SessionProvider({ children }: { children?: ReactNode }) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const markUnauthorized = useCallback(() => {
    setSession(anonymousSession);
    configureApiSession(null, markUnauthorized);
  }, []);

  const applySession = useCallback((next: AdminSession) => {
    setSession(next);
    configureApiSession(next.csrf_token ?? null, markUnauthorized);
  }, [markUnauthorized]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      applySession(await getSession());
    } catch (reason) {
      configureApiSession(null, markUnauthorized);
      setSession(anonymousSession);
      setError(errorMessage(reason));
    }
  }, [applySession, markUnauthorized]);

  useEffect(() => {
    let active = true;
    getSession()
      .then((next) => {
        if (active) {
          applySession(next);
        }
      })
      .catch((reason) => {
        if (active) {
          setSession(anonymousSession);
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [applySession]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    applySession(await loginRequest(username, password));
  }, [applySession]);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      markUnauthorized();
    }
  }, [markUnauthorized]);

  const value = useMemo(
    () => ({ session, loading, error, login, logout, refresh }),
    [session, loading, error, login, logout, refresh],
  );

  return (
    <SessionContext.Provider value={value}>
      {children ?? <Outlet />}
    </SessionContext.Provider>
  );
}

export function RequireSession() {
  const location = useLocation();
  const { session, loading } = useSession();

  if (loading) {
    return <main className="session-loading" aria-live="polite">正在检查登录状态…</main>;
  }
  if (!session?.authenticated) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <Outlet />;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return value;
}

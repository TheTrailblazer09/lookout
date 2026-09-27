/**
 * Who is signed in, for the whole app.
 *
 * The token lives in localStorage so a refresh does not sign you out. On
 * boot we ask /auth/me once: that both restores the session and proves the
 * token is still valid, so a stale one gets cleared instead of causing
 * confusing 401s later.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { api, tokenStore } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!tokenStore.get()) {
      setLoading(false);
      return () => {};
    }
    api
      .me()
      .then((d) => !cancelled && setUser(d.user))
      .catch(() => tokenStore.clear())
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const finish = useCallback((data) => {
    tokenStore.set(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      signIn: async (email, password) => finish(await api.login(email, password)),
      signUp: async (email, password, displayName) =>
        finish(await api.register(email, password, displayName)),
      signOut: () => {
        tokenStore.clear();
        setUser(null);
      },
    }),
    [user, loading, finish]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** Wraps pages that need a signed-in user. */
export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="auth-booting">Checking your session…</div>;
  // remember where they were headed, so sign-in can send them back there
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return children;
}
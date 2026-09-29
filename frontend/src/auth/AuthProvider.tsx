import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import * as api from "../api/endpoints";
import { AuthContext, type AuthState } from "./context";
import { clearAccessToken, onSessionEnded, refreshAccessToken } from "./tokenStore";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const signedOut = useCallback(() => {
    clearAccessToken();
    queryClient.clear();
    setState({ status: "anonymous", user: null });
  }, [queryClient]);

  // On first load there is no access token in memory (ADR-0006), but
  // the refresh cookie may still hold a live session: try it once.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const restored = (await refreshAccessToken()) ? await api.getMe().catch(() => null) : null;
      if (cancelled) return;
      setState(restored ? { status: "authenticated", user: restored } : { status: "anonymous", user: null });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => onSessionEnded(signedOut), [signedOut]);

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
    const user = await api.getMe();
    setState({ status: "authenticated", user });
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      signedOut();
    }
  }, [signedOut]);

  const refreshUser = useCallback(async () => {
    const user = await api.getMe();
    setState({ status: "authenticated", user });
  }, []);

  const value = useMemo(
    () => ({ ...state, login, logout, refreshUser }),
    [state, login, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

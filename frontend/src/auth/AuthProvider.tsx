import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { AuthContext, type AuthState } from "./context";
import {
  clearAccessToken,
  clearSignedOutMark,
  isMarkedSignedOut,
  markSignedOut,
  onSessionEnded,
  refreshAccessToken,
  setSessionScope,
  authTiming,
  type SessionScope,
} from "./tokenStore";

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** /admin/... is the admin console; everything else is the customer site. */
function scopeOf(pathname: string): SessionScope {
  return pathname === "/admin" || pathname.startsWith("/admin/") ? "admin" : "customer";
}

type Restored = { kind: "user"; user: api.CurrentUser } | { kind: "none" } | { kind: "unreachable" };

/** One attempt to restore this app's session from its refresh cookie. */
async function restoreOnce(): Promise<Restored> {
  const refreshed = await refreshAccessToken();
  if (refreshed === "invalid") return { kind: "none" };
  if (refreshed === "unavailable") return { kind: "unreachable" };
  try {
    return { kind: "user", user: await api.getMe() };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return { kind: "none" };
    }
    return { kind: "unreachable" };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const scope = scopeOf(useLocation().pathname);
  const [attempt, setAttempt] = useState(0);
  // Each session check is identified by this key; a result recorded for
  // an older check (another app, an earlier attempt) reads as "loading".
  const checkKey = `${scope}:${attempt}`;
  const [recorded, setRecorded] = useState<{ key: string; state: AuthState } | null>(null);
  const state = useMemo<AuthState>(
    () => (recorded?.key === checkKey ? recorded.state : { status: "loading", user: null }),
    [recorded, checkKey],
  );
  const setState = useCallback(
    (next: AuthState) => setRecorded({ key: checkKey, state: next }),
    [checkKey],
  );

  const signedOut = useCallback(() => {
    clearAccessToken();
    queryClient.clear();
    setState({ status: "anonymous", user: null });
  }, [queryClient, setState]);

  // On load (and on switching between the customer site and the admin
  // console) there is no access token in memory (ADR-0006), but this
  // app's refresh cookie may hold a live session. Only a definite answer
  // from the server decides: "no session" shows the sign-in page, a
  // network or server error is retried and never mistaken for either.
  useEffect(() => {
    let cancelled = false;
    setSessionScope(scope);
    (async () => {
      if (isMarkedSignedOut(scope)) {
        // The user signed out but the server didn't hear it: try again,
        // and stay signed out whatever happens.
        try {
          await api.logout();
          clearSignedOutMark(scope);
        } catch {
          // Still unreachable; retried on the next load.
        }
        if (!cancelled) setState({ status: "anonymous", user: null });
        return;
      }
      for (const delay of [0, ...authTiming.retryDelaysMs]) {
        if (delay) await pause(delay);
        if (cancelled) return;
        const restored = await restoreOnce();
        if (cancelled) return;
        if (restored.kind === "user") {
          setState({ status: "authenticated", user: restored.user });
          return;
        }
        if (restored.kind === "none") {
          setState({ status: "anonymous", user: null });
          return;
        }
      }
      setState({ status: "unavailable", user: null });
    })();
    return () => {
      cancelled = true;
    };
  }, [scope, attempt, setState]);

  useEffect(() => onSessionEnded(signedOut), [signedOut]);

  const login = useCallback(
    async (email: string, password: string) => {
      await api.login(email, password);
      clearSignedOutMark(scope);
      const user = await api.getMe();
      setState({ status: "authenticated", user });
    },
    [scope, setState],
  );

  const logout = useCallback(async () => {
    let revoked = false;
    for (const delay of [0, ...authTiming.retryDelaysMs]) {
      if (delay) await pause(delay);
      try {
        await api.logout();
        revoked = true;
        break;
      } catch {
        // Retried below; the marker covers the case where none succeed.
      }
    }
    if (revoked) clearSignedOutMark(scope);
    else markSignedOut(scope);
    signedOut();
  }, [scope, signedOut]);

  const refreshUser = useCallback(async () => {
    const user = await api.getMe();
    setState({ status: "authenticated", user });
  }, [setState]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo(
    () => ({ ...state, login, logout, refreshUser, retry }),
    [state, login, logout, refreshUser, retry],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

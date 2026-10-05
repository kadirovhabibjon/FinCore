// ADR-0006: the access token lives only in this module's memory — never
// localStorage/sessionStorage, where any injected script could read it.
// A page reload loses it on purpose; the httpOnly refresh cookie (which
// no script can read) gets a fresh one back via `refreshAccessToken`.

/** The customer site and the admin console are separate sessions with
 * separate refresh cookies: signing in to one never signs you in to the
 * other (identity-service's "cookie" / "cookie-admin" transports). */
export type SessionScope = "customer" | "admin";

/** How a refresh attempt ended. "unavailable" (network down, server
 * restarting, rate limited) says nothing about the session itself, so it
 * must never be treated as being signed out. */
export type RefreshResult = "ok" | "invalid" | "unavailable";

/** Waits between attempts to reach the server on page load, and between
 * sign-out attempts. Tests shorten them. */
export const authTiming = {
  retryDelaysMs: [500, 1500, 3000],
  requestTimeoutMs: 8000,
  /** No interaction for this long signs the user out (see lastActivity). */
  idleTimeoutMs: 15 * 60 * 1000,
  idleCheckIntervalMs: 15_000,
};

const TRANSPORT: Record<SessionScope, string> = { customer: "cookie", admin: "cookie-admin" };

let scope: SessionScope = "customer";
let accessToken: string | null = null;
let inFlightRefresh: Promise<RefreshResult> | null = null;
const sessionEndedListeners = new Set<() => void>();

export function getSessionScope(): SessionScope {
  return scope;
}

/** Switching apps drops the other app's access token. */
export function setSessionScope(next: SessionScope): void {
  if (next !== scope) {
    scope = next;
    accessToken = null;
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string): void {
  accessToken = token;
}

export function clearAccessToken(): void {
  accessToken = null;
}

export function refreshTransportHeaders(): Record<string, string> {
  return { "X-Refresh-Token-Transport": TRANSPORT[scope] };
}

/**
 * Exchanges the refresh cookie for a new access token. Single-flight:
 * refresh tokens are one-time-use and reuse revokes the whole session,
 * so several requests hitting 401 at once must share one refresh call
 * rather than each spending the same cookie.
 */
export function refreshAccessToken(): Promise<RefreshResult> {
  inFlightRefresh ??= (async (): Promise<RefreshResult> => {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", ...refreshTransportHeaders() },
        // A hung request counts as "unavailable", not as a long blank wait.
        signal: AbortSignal.timeout(authTiming.requestTimeoutMs),
      });
      if (response.status === 401 || response.status === 403) {
        clearAccessToken();
        return "invalid";
      }
      if (!response.ok) return "unavailable";
      const body = (await response.json()) as { access_token: string };
      setAccessToken(body.access_token);
      return "ok";
    } catch {
      return "unavailable";
    } finally {
      inFlightRefresh = null;
    }
  })();
  return inFlightRefresh;
}

/** Notified when an authenticated request fails and refreshing can't
 * recover it — the AuthProvider uses this to drop back to signed-out. */
export function onSessionEnded(listener: () => void): () => void {
  sessionEndedListeners.add(listener);
  return () => sessionEndedListeners.delete(listener);
}

export function endSession(): void {
  clearAccessToken();
  sessionEndedListeners.forEach((listener) => listener());
}

// --- "signed out here" marker -------------------------------------------
//
// Signing out has to reach the server: the refresh cookie is httpOnly, so
// only identity-service can revoke and clear it. If that request fails
// (offline, server restarting), this marker remembers that the user chose
// to sign out, so the next page load stays signed out and retries the
// server-side sign-out instead of quietly restoring the session.

const markerKey = (which: SessionScope) => `fincore:signed-out:${which}`;

export function markSignedOut(which: SessionScope): void {
  try {
    localStorage.setItem(markerKey(which), "1");
  } catch {
    // Storage blocked: the in-memory sign-out still applies to this tab.
  }
}

export function clearSignedOutMark(which: SessionScope): void {
  try {
    localStorage.removeItem(markerKey(which));
  } catch {
    // Nothing stored.
  }
}

export function isMarkedSignedOut(which: SessionScope): boolean {
  try {
    return localStorage.getItem(markerKey(which)) === "1";
  } catch {
    return false;
  }
}

// --- last activity ----------------------------------------------------------
//
// When the user last touched this app, kept in localStorage so it outlives
// the tab. Someone who leaves without signing out and comes back later -
// same tab, new tab or after closing the browser - is asked to sign in
// again, instead of the still-valid refresh cookie letting them straight in.
// identity-service enforces its own (longer) idle limit as the backstop.

const activityKey = (which: SessionScope) => `fincore:last-activity:${which}`;

export function recordActivity(which: SessionScope, at: number = Date.now()): void {
  try {
    localStorage.setItem(activityKey(which), String(at));
  } catch {
    // Storage blocked: the server-side idle limit still applies.
  }
}

export function clearActivity(which: SessionScope): void {
  try {
    localStorage.removeItem(activityKey(which));
  } catch {
    // Nothing stored.
  }
}

/** True when activity was recorded and it is older than the idle limit. */
export function isIdleExpired(which: SessionScope, now: number = Date.now()): boolean {
  try {
    const stored = Number(localStorage.getItem(activityKey(which)));
    return stored > 0 && now - stored > authTiming.idleTimeoutMs;
  } catch {
    return false;
  }
}

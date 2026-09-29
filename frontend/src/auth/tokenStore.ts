// ADR-0006: the access token lives only in this module's memory — never
// localStorage/sessionStorage, where any injected script could read it.
// A page reload loses it on purpose; the httpOnly refresh cookie (which
// no script can read) gets a fresh one back via `refreshAccessToken`.

const REFRESH_HEADER = { "X-Refresh-Token-Transport": "cookie" } as const;

let accessToken: string | null = null;
let inFlightRefresh: Promise<boolean> | null = null;
const sessionEndedListeners = new Set<() => void>();

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
  return { ...REFRESH_HEADER };
}

/**
 * Exchanges the refresh cookie for a new access token. Single-flight:
 * refresh tokens are one-time-use and reuse revokes the whole session,
 * so several requests hitting 401 at once must share one refresh call
 * rather than each spending the same cookie.
 */
export function refreshAccessToken(): Promise<boolean> {
  inFlightRefresh ??= (async () => {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", ...REFRESH_HEADER },
      });
      if (!response.ok) {
        clearAccessToken();
        return false;
      }
      const body = (await response.json()) as { access_token: string };
      setAccessToken(body.access_token);
      return true;
    } catch {
      clearAccessToken();
      return false;
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

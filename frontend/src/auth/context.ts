import { createContext, useContext } from "react";

import type { CurrentUser } from "../api/endpoints";

export type Role = "USER" | "SUPPORT" | "ADMIN";

export type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  // The server couldn't be reached to check the session: neither signed
  // in nor signed out yet, so neither the app nor the sign-in page shows.
  | { status: "unavailable"; user: null }
  | { status: "authenticated"; user: CurrentUser };

export type AuthContextValue = AuthState & {
  /** Checks the session again after "unavailable". */
  retry: () => void;
  /** `identifier` is a phone number or an email address. */
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Hiding a control is a convenience; every service checks the role
 * again on the request itself. */
export function hasAnyRole(user: CurrentUser | null, ...roles: Role[]): boolean {
  return !!user && roles.some((role) => user.roles.includes(role));
}

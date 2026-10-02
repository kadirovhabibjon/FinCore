import { Navigate, Outlet, useLocation } from "react-router-dom";

import { hasAnyRole, useAuth, type Role } from "./context";

function FullPageMessage({ text }: { text: string }) {
  return (
    <div className="center-page" role="status">
      {text}
    </div>
  );
}

/** `loginPath` differs per app: the customer site signs in at /login,
 * the admin console at /admin/login. */
export function RequireAuth({ loginPath = "/login" }: { loginPath?: string }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <FullPageMessage text="Loading…" />;
  if (auth.status === "anonymous") {
    return (
      <Navigate to={loginPath} replace state={{ from: location.pathname + location.search }} />
    );
  }
  return <Outlet />;
}

/** The admin console's door: a signed-in account without a staff role
 * gets no further than this. (The APIs check the role again anyway.) */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { user, logout } = useAuth();
  if (!hasAnyRole(user, ...roles)) {
    return (
      <div className="auth-page">
        <div className="card auth-card">
          <h1>No admin access</h1>
          <p className="muted">
            {user?.email} is not a staff account. The admin console needs one of these roles:{" "}
            {roles.join(", ")}.
          </p>
          <button type="button" className="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </div>
    );
  }
  return <Outlet />;
}

/** Login/register: a signed-in user has no business here. This is also
 * what moves the user on after a successful login — back to the page
 * RequireAuth bounced them from, if any. */
export function RedirectIfAuthenticated({ home = "/" }: { home?: string }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <FullPageMessage text="Loading…" />;
  if (auth.status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? home} replace />;
  }
  return <Outlet />;
}

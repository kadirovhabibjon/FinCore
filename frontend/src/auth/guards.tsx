import { Navigate, Outlet, useLocation } from "react-router-dom";

import { hasAnyRole, useAuth, type Role } from "./context";

function FullPageMessage({ text }: { text: string }) {
  return (
    <div className="center-page" role="status">
      {text}
    </div>
  );
}

export function RequireAuth() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <FullPageMessage text="Loading…" />;
  if (auth.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

export function RequireRole({ roles }: { roles: Role[] }) {
  const { user } = useAuth();
  if (!hasAnyRole(user, ...roles)) {
    return (
      <section className="page">
        <h1>Not allowed</h1>
        <p className="muted">This area needs one of these roles: {roles.join(", ")}.</p>
      </section>
    );
  }
  return <Outlet />;
}

/** Login/register: a signed-in user has no business here. This is also
 * what moves the user on after a successful login — back to the page
 * RequireAuth bounced them from, if any. */
export function RedirectIfAuthenticated() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return <FullPageMessage text="Loading…" />;
  if (auth.status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from ?? "/"} replace />;
  }
  return <Outlet />;
}

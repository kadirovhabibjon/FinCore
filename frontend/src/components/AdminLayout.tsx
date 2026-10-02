import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/context";

const LINKS = [
  { to: "/admin/reviews", label: "Fraud reviews" },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/transactions", label: "Transactions" },
  { to: "/admin/webhooks", label: "Webhooks" },
];

/** The admin console (ADR-0005): its own app at /admin, with its own
 * sign-in page and navigation, never linked from the customer site. */
export function AdminLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <NavLink to="/admin" end className="admin-brand">
          FinCore <span>Admin</span>
        </NavLink>
        <nav className="admin-nav" aria-label="Admin">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className="admin-nav-link">
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="admin-account">
          <div className="small">{user?.email}</div>
          <div className="muted small">{user?.roles.filter((r) => r !== "USER").join(", ")}</div>
          <button type="button" className="button button-small button-ghost" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}

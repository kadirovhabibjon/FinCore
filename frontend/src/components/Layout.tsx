import { NavLink, Outlet } from "react-router-dom";

import { hasAnyRole, useAuth } from "../auth/context";

const USER_LINKS = [
  { to: "/", label: "Wallets", end: true },
  { to: "/transfer", label: "Send" },
  { to: "/pay", label: "Pay" },
  { to: "/transactions", label: "History" },
  { to: "/merchants", label: "Merchants" },
];

const STAFF_LINKS = [
  { to: "/admin/users", label: "Users" },
  { to: "/admin/reviews", label: "Reviews" },
  { to: "/admin/transactions", label: "Transactions" },
  { to: "/admin/webhooks", label: "Webhooks" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const isStaff = hasAnyRole(user, "SUPPORT", "ADMIN");

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          FinCore
        </NavLink>
        <nav className="nav" aria-label="Main">
          {USER_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className="nav-link">
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          <NavLink to="/settings" className="nav-link">
            {user?.first_name ?? "Account"}
          </NavLink>
          <button type="button" className="button button-ghost" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      {isStaff && (
        <nav className="staffbar" aria-label="Admin">
          <span className="staffbar-label">Admin</span>
          {STAFF_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} className="nav-link">
              {link.label}
            </NavLink>
          ))}
        </nav>
      )}
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

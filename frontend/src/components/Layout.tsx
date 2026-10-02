import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/context";
import { ChatWidget } from "./ChatWidget";

const USER_LINKS = [
  { to: "/", label: "Wallets", end: true },
  { to: "/transfer", label: "Send" },
  { to: "/pay", label: "Pay" },
  { to: "/transactions", label: "History" },
  { to: "/merchants", label: "Merchants" },
];

/** The customer site's shell. Deliberately knows nothing about the admin
 * console, which is a separate app at /admin with its own layout
 * (AdminLayout) — even a staff account sees only the customer menu here. */
export function Layout() {
  const { user, logout } = useAuth();

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
      <main className="content">
        <Outlet />
      </main>
      <ChatWidget />
    </div>
  );
}

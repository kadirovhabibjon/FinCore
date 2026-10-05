import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/context";
import { ChatWidget } from "./ChatWidget";
import { NotificationBell } from "./NotificationBell";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="nav-icon"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const USER_LINKS = [
  {
    to: "/",
    label: "Wallets",
    end: true,
    icon: (
      <Icon>
        <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H18a2 2 0 0 1 2 2v1" />
        <path d="M3 7.5V17a3 3 0 0 0 3 3h13a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2H5.5A2.5 2.5 0 0 1 3 7.5Z" />
        <circle cx="16.5" cy="14" r="1.2" fill="currentColor" stroke="none" />
      </Icon>
    ),
  },
  {
    to: "/transfer",
    label: "Send",
    icon: (
      <Icon>
        <path d="M21 3 10.5 13.5" />
        <path d="M21 3 14.5 21l-4-7.5L3 9.5 21 3Z" />
      </Icon>
    ),
  },
  {
    to: "/pay",
    label: "Pay",
    icon: (
      <Icon>
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
        <path d="M2.5 10h19M6.5 15h4" />
      </Icon>
    ),
  },
  {
    to: "/transactions",
    label: "History",
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3.5 2" />
      </Icon>
    ),
  },
  {
    to: "/merchants",
    label: "Merchants",
    icon: (
      <Icon>
        <path d="M4 9.5 5.2 4h13.6L20 9.5" />
        <path d="M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0" />
        <path d="M5.5 12.5V20h13v-7.5M10 20v-4.5h4V20" />
      </Icon>
    ),
  },
];

/** The customer site's shell. Deliberately knows nothing about the admin
 * console, which is a separate app at /admin with its own layout
 * (AdminLayout) — even a staff account sees only the customer menu here.
 *
 * One markup, two arrangements (styles.css): on wide screens the main
 * navigation sits in the top bar; on phones the same <nav> becomes a tab
 * bar fixed to the bottom of the screen, within thumb reach. */
export function Layout() {
  const { user, logout } = useAuth();
  const name = user?.first_name ?? "Account";

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          FinCore
        </NavLink>
        <nav className="nav" aria-label="Main">
          {USER_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className="nav-link">
              {link.icon}
              <span>{link.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          <NotificationBell />
          <NavLink to="/settings" className="nav-link account-link" title="Account">
            <span className="avatar" aria-hidden="true">
              {name.charAt(0).toUpperCase()}
            </span>
            <span className="account-name">{name}</span>
          </NavLink>
          <button
            type="button"
            className="button button-ghost signout"
            onClick={() => void logout()}
          >
            <svg
              className="signout-icon"
              viewBox="0 0 24 24"
              width="20"
              height="20"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              focusable="false"
            >
              <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3" />
              <path d="M15 8l4 4-4 4M19 12H9" />
            </svg>
            <span className="signout-text">Sign out</span>
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

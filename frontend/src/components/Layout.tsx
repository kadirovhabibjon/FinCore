import { Suspense, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/context";
import { PageSkeleton } from "./Skeleton";
import { ChatWidget } from "./ChatWidget";
import { HistoryIcon, PayIcon, SendIcon, ShopIcon, SignOutIcon, WalletIcon } from "./icons";
import { NotificationBell } from "./NotificationBell";
import { useI18n, type MessageKey } from "../i18n";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeButton } from "./ThemeSwitch";

const USER_LINKS: { to: string; label: MessageKey; end?: boolean; icon: ReactNode }[] = [
  {
    to: "/",
    label: "nav.wallets",
    end: true,
    icon: <WalletIcon className="nav-icon" />,
  },
  {
    to: "/transfer",
    label: "nav.send",
    icon: <SendIcon className="nav-icon" />,
  },
  {
    to: "/pay",
    label: "nav.pay",
    icon: <PayIcon className="nav-icon" />,
  },
  {
    to: "/transactions",
    label: "nav.history",
    icon: <HistoryIcon className="nav-icon" />,
  },
  {
    to: "/merchants",
    label: "nav.merchants",
    icon: <ShopIcon className="nav-icon" />,
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
  const { t } = useI18n();
  const name = user?.first_name ?? t("nav.account");

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          FinCore
        </NavLink>
        <nav className="nav" aria-label={t("nav.main")}>
          {USER_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className="nav-link">
              {link.icon}
              <span>{t(link.label)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          <NotificationBell />
          <ThemeButton />
          <LanguageSwitch />
          <NavLink to="/settings" className="nav-link account-link" title={t("nav.account")}>
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
            <SignOutIcon size={20} className="signout-icon" />
            <span className="signout-text">{t("common.signOut")}</span>
          </button>
        </div>
      </header>
      <main className="content">
        <Suspense fallback={<PageSkeleton />}>
          <Outlet />
        </Suspense>
      </main>
      <ChatWidget />
    </div>
  );
}

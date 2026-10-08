import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { useI18n, type MessageKey } from "../i18n";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeButton } from "./ThemeSwitch";

type Counted = "reviews" | "support";

const LINKS: { to: string; label: MessageKey; end?: boolean; count?: Counted }[] = [
  { to: "/admin", label: "admin.nav.dashboard", end: true },
  { to: "/admin/reviews", label: "admin.nav.reviews", count: "reviews" },
  { to: "/admin/users", label: "admin.nav.users" },
  { to: "/admin/transactions", label: "admin.nav.transactions" },
  { to: "/admin/webhooks", label: "admin.nav.webhooks" },
  { to: "/admin/announcements", label: "admin.nav.announcements" },
  { to: "/admin/support", label: "admin.nav.support", count: "support" },
];

const WHAT: Record<Counted, MessageKey> = {
  reviews: "admin.nav.waitingReviews",
  support: "admin.nav.unreadSupport",
};

/** The admin console (ADR-0005): its own app at /admin, with its own
 * sign-in page and navigation, never linked from the customer site.
 *
 * The menu counts what is waiting for staff - operations in the review
 * queue, customers' messages nobody has opened - so it is seen from
 * whichever page is open. Polled with the same queries those pages use;
 * a count that can't be read is left out rather than shown as zero. */
export function AdminLayout() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const reviews = useQuery({
    queryKey: ["admin", "reviews"],
    queryFn: api.adminListReviews,
    refetchInterval: 15_000,
  });
  const support = useQuery({
    queryKey: ["admin", "support", "inbox", "open"],
    queryFn: () => api.adminSupportInbox("OPEN"),
    refetchInterval: 10_000,
  });
  const counts: Record<Counted, number> = {
    reviews: reviews.data?.length ?? 0,
    support: support.data?.unread_count ?? 0,
  };

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <NavLink to="/admin" end className="admin-brand">
          FinCore <span>Admin</span>
        </NavLink>
        <nav className="admin-nav" aria-label={t("admin.nav.label")}>
          {LINKS.map((link) => {
            const count = link.count ? counts[link.count] : 0;
            return (
              <NavLink key={link.to} to={link.to} end={link.end} className="admin-nav-link">
                {t(link.label)}
                {link.count && count > 0 && (
                  <span className="admin-count" aria-label={t(WHAT[link.count], { count })}>
                    {count > 99 ? "99+" : count}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
        <div className="admin-account">
          <div className="small">{user?.email}</div>
          <div className="muted small">{user?.roles.filter((r) => r !== "USER").join(", ")}</div>
          <div className="admin-account-actions">
            <button
              type="button"
              className="button button-small button-ghost"
              onClick={() => void logout()}
            >
              {t("admin.signOut")}
            </button>
            <ThemeButton />
            <LanguageSwitch />
          </div>
        </div>
      </aside>
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}

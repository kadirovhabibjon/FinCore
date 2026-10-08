import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ThemeButton } from "./ThemeSwitch";

const LINKS = [
  { to: "/admin/reviews", label: "Fraud reviews", count: "reviews" },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/transactions", label: "Transactions" },
  { to: "/admin/webhooks", label: "Webhooks" },
  { to: "/admin/announcements", label: "Announcements" },
  { to: "/admin/support", label: "Support", count: "support" },
] as const;

const WHAT: Record<"reviews" | "support", string> = {
  reviews: "waiting for a decision",
  support: "unread",
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
  const counts = { reviews: reviews.data?.length ?? 0, support: support.data?.unread_count ?? 0 };

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <NavLink to="/admin" end className="admin-brand">
          FinCore <span>Admin</span>
        </NavLink>
        <nav className="admin-nav" aria-label="Admin">
          {LINKS.map((link) => {
            const count = "count" in link ? counts[link.count] : 0;
            return (
              <NavLink key={link.to} to={link.to} className="admin-nav-link">
                {link.label}
                {count > 0 && "count" in link && (
                  <span className="admin-count" aria-label={`${count} ${WHAT[link.count]}`}>
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
              Sign out
            </button>
            <ThemeButton />
          </div>
        </div>
      </aside>
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}

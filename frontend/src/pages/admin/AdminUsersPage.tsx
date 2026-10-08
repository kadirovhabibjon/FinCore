import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { DateTime, Empty, ErrorAlert, Loading, Pager, StatusBadge } from "../../components/ui";

const PAGE_SIZE = 25;
const STATUSES: api.UserStatus[] = ["ACTIVE", "SUSPENDED", "BLOCKED"];

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const isAdmin = hasAnyRole(me, "ADMIN");
  const queryClient = useQueryClient();
  // The search lives in the URL (?q=), so other pages can link to one
  // customer here and a search can be bookmarked or sent to a colleague.
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const [draft, setDraft] = useState(query);
  const [offset, setOffset] = useState(0);
  // A status chosen but not yet confirmed: taking someone's access away
  // signs them out everywhere, so it is not done by a slip of the mouse.
  const [pending, setPending] = useState<{ user: api.AdminUser; status: api.UserStatus } | null>(
    null,
  );

  const users = useQuery({
    queryKey: ["admin", "users", query, offset],
    queryFn: () => api.adminSearchUsers(query, { limit: PAGE_SIZE, offset }),
  });
  const setStatus = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: api.UserStatus }) =>
      api.adminSetUserStatus(userId, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "user"] });
      return queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onSettled: () => setPending(null),
  });

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setParams(draft.trim() ? { q: draft.trim() } : {});
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Users</h1>
          <p className="muted">
            Search by email, phone or user id.{" "}
            {isAdmin
              ? "Suspending or blocking a user signs them out everywhere."
              : "Changing a user's status needs the ADMIN role."}
          </p>
        </div>
        <form className="inline-form" onSubmit={onSearch} role="search">
          <input
            aria-label="Search users"
            placeholder="email, phone or id"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="button">
            Search
          </button>
        </form>
      </header>
      <ErrorAlert error={users.error ?? setStatus.error} />
      {pending && (
        <div className="alert alert-info confirm-bar" role="alertdialog" aria-label="Confirm">
          <span>
            Set <strong>{pending.user.email}</strong> to <strong>{pending.status}</strong>?
            {pending.status !== "ACTIVE" && " They are signed out everywhere and can't sign in."}
          </span>
          <span className="actions">
            <button
              type="button"
              className="button button-small button-ghost"
              onClick={() => setPending(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`button button-small ${pending.status === "ACTIVE" ? "" : "button-danger"}`}
              disabled={setStatus.isPending}
              onClick={() =>
                setStatus.mutate({ userId: pending.user.id, status: pending.status })
              }
            >
              Confirm
            </button>
          </span>
        </div>
      )}
      {users.isPending ? (
        <Loading what="Searching" />
      ) : users.data?.length === 0 && offset === 0 ? (
        <Empty>No users match.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email / phone</th>
                <th>Roles</th>
                <th>Joined</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.map((user) => (
                <tr key={user.id}>
                  <td data-label="Name">
                    {user.first_name} {user.last_name}
                    <div className="small">
                      <Link to={`/admin/transactions?user_id=${user.id}`}>transactions</Link>
                      {" · "}
                      <Link to={`/admin/support?user=${user.id}`}>messages</Link>
                    </div>
                  </td>
                  <td data-label="Email / phone">
                    {user.email}
                    <div className="muted small">{user.phone}</div>
                  </td>
                  <td data-label="Roles">{user.roles.join(", ")}</td>
                  <td data-label="Joined">
                    <DateTime value={user.created_at} />
                  </td>
                  <td data-label="Status">
                    {isAdmin && user.id !== me?.id ? (
                      <select
                        aria-label={`Status of ${user.email}`}
                        value={pending?.user.id === user.id ? pending.status : user.status}
                        disabled={setStatus.isPending}
                        onChange={(e) => {
                          const status = e.target.value as api.UserStatus;
                          setPending(status === user.status ? null : { user, status });
                        }}
                      >
                        {STATUSES.map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    ) : (
                      <StatusBadge status={user.status} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={users.data?.length ?? 0}
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}

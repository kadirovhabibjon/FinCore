import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { DateTime, Empty, ErrorAlert, Loading, Pager, StatusBadge } from "../../components/ui";

const PAGE_SIZE = 25;
const STATUSES: api.UserStatus[] = ["ACTIVE", "SUSPENDED", "BLOCKED"];

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const isAdmin = hasAnyRole(me, "ADMIN");
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);

  const users = useQuery({
    queryKey: ["admin", "users", query, offset],
    queryFn: () => api.adminSearchUsers(query, { limit: PAGE_SIZE, offset }),
  });
  const setStatus = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: api.UserStatus }) =>
      api.adminSetUserStatus(userId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQuery(draft.trim());
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
                  <td>
                    {user.first_name} {user.last_name}
                    <div className="small">
                      <Link to={`/admin/transactions?user_id=${user.id}`}>transactions</Link>
                    </div>
                  </td>
                  <td>
                    {user.email}
                    <div className="muted small">{user.phone}</div>
                  </td>
                  <td>{user.roles.join(", ")}</td>
                  <td>
                    <DateTime value={user.created_at} />
                  </td>
                  <td>
                    {isAdmin && user.id !== me?.id ? (
                      <select
                        aria-label={`Status of ${user.email}`}
                        value={user.status}
                        disabled={setStatus.isPending}
                        onChange={(e) =>
                          setStatus.mutate({
                            userId: user.id,
                            status: e.target.value as api.UserStatus,
                          })
                        }
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

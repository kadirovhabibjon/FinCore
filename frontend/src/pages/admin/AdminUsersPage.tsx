import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { DateTime, Empty, ErrorAlert, Loading, Pager, StatusBadge } from "../../components/ui";
import { useI18n } from "../../i18n";

const PAGE_SIZE = 25;
const STATUSES: api.UserStatus[] = ["ACTIVE", "SUSPENDED", "BLOCKED"];

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const { t, tr, maybe } = useI18n();
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
          <h1>{t("admin.users.title")}</h1>
          <p className="muted">
            {t("admin.users.intro")}{" "}
            {isAdmin ? t("admin.users.adminNote") : t("admin.users.supportNote")}
          </p>
        </div>
        <form className="inline-form" onSubmit={onSearch} role="search">
          <input
            aria-label={t("admin.users.searchLabel")}
            placeholder={t("admin.users.searchPlaceholder")}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="button">
            {t("admin.users.search")}
          </button>
        </form>
      </header>
      <ErrorAlert error={users.error ?? setStatus.error} />
      {pending && (
        <div className="alert alert-info confirm-bar" role="alertdialog" aria-label={t("admin.users.confirmLabel")}>
          <span>
            {tr("admin.users.setTo", {
              email: <strong>{pending.user.email}</strong>,
              status: <strong>{pending.status}</strong>,
            })}
            {pending.status !== "ACTIVE" && ` ${t("admin.users.signedOut")}`}
          </span>
          <span className="actions">
            <button
              type="button"
              className="button button-small button-ghost"
              onClick={() => setPending(null)}
            >
              {t("admin.users.cancel")}
            </button>
            <button
              type="button"
              className={`button button-small ${pending.status === "ACTIVE" ? "" : "button-danger"}`}
              disabled={setStatus.isPending}
              onClick={() =>
                setStatus.mutate({ userId: pending.user.id, status: pending.status })
              }
            >
              {t("admin.users.confirm")}
            </button>
          </span>
        </div>
      )}
      {users.isPending ? (
        <Loading what={t("admin.users.searching")} />
      ) : users.data?.length === 0 && offset === 0 ? (
        <Empty>{t("admin.users.empty")}</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("admin.users.name")}</th>
                <th>{t("admin.users.contact")}</th>
                <th>{t("admin.users.roles")}</th>
                <th>{t("admin.users.joined")}</th>
                <th>{t("admin.col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.map((user) => (
                <tr key={user.id}>
                  <td data-label={t("admin.users.name")}>
                    <Link to={`/admin/users/${user.id}`}>
                      {user.first_name} {user.last_name}
                    </Link>
                    <div className="small">
                      <Link to={`/admin/transactions?user_id=${user.id}`}>
                        {t("admin.users.transactions")}
                      </Link>
                      {" · "}
                      <Link to={`/admin/support?user=${user.id}`}>{t("admin.users.messages")}</Link>
                    </div>
                  </td>
                  <td data-label={t("admin.users.contact")}>
                    {user.email}
                    <div className="muted small">{user.phone}</div>
                  </td>
                  <td data-label={t("admin.users.roles")}>{user.roles.join(", ")}</td>
                  <td data-label={t("admin.users.joined")}>
                    <DateTime value={user.created_at} />
                  </td>
                  <td data-label={t("admin.col.status")}>
                    {isAdmin && user.id !== me?.id ? (
                      <select
                        aria-label={t("admin.users.statusOf", { email: user.email })}
                        value={pending?.user.id === user.id ? pending.status : user.status}
                        disabled={setStatus.isPending}
                        onChange={(e) => {
                          const status = e.target.value as api.UserStatus;
                          setPending(status === user.status ? null : { user, status });
                        }}
                      >
                        {STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {maybe(`status.${status}`) ?? status}
                          </option>
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

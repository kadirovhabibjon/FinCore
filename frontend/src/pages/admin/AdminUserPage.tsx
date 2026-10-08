import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import {
  DateTime,
  Empty,
  ErrorAlert,
  Loading,
  Money,
  ShortId,
  StatusBadge,
} from "../../components/ui";
import { useI18n } from "../../i18n";
import { formatCardNumber } from "../../lib/card";
import { reasonText } from "../../lib/reasons";

const LATEST = 10;

/** One customer on one page: who they are, their wallets, what they
 * did lately and what they wrote to support. Each part comes from its
 * own service and loads on its own. Nothing here changes anything -
 * status is changed on the Users page, conversations are answered on
 * the Support page. */
export function AdminUserPage() {
  const { userId = "" } = useParams();
  const { t } = useI18n();
  const user = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => api.adminGetUser(userId),
  });

  if (user.isPending) return <Loading what={t("admin.user.loading")} />;
  if (user.error) {
    return (
      <section className="page">
        <p>
          <Link to="/admin/users">{t("admin.user.back")}</Link>
        </p>
        <ErrorAlert error={user.error} />
      </section>
    );
  }
  const profile = user.data;

  return (
    <section className="page">
      <p>
        <Link to="/admin/users">{t("admin.user.back")}</Link>
      </p>
      <header className="page-header">
        <div>
          <h1>
            {profile.first_name} {profile.last_name}
          </h1>
          <p className="muted">
            {profile.email} · {profile.phone}
          </p>
        </div>
        <StatusBadge status={profile.status} />
      </header>

      <h2>{t("admin.user.profile")}</h2>
      <dl className="card details">
        <dt>{t("common.email")}</dt>
        <dd>{profile.email}</dd>
        <dt>{t("settings.phone")}</dt>
        <dd>{profile.phone}</dd>
        <dt>{t("settings.roles")}</dt>
        <dd>{profile.roles.join(", ")}</dd>
        <dt>{t("admin.user.joined")}</dt>
        <dd>
          <DateTime value={profile.created_at} />
        </dd>
        <dt>{t("settings.userId")}</dt>
        <dd>
          <code>{profile.id}</code>
        </dd>
      </dl>

      <h2>{t("admin.user.wallets")}</h2>
      <Wallets userId={userId} />

      <h2>{t("admin.user.operations")}</h2>
      <Operations userId={userId} />

      <h2>{t("admin.user.support")}</h2>
      <Support userId={userId} />
    </section>
  );
}

function Wallets({ userId }: { userId: string }) {
  const { t } = useI18n();
  const wallets = useQuery({
    queryKey: ["admin", "wallets", userId],
    queryFn: () => api.adminListWallets(userId),
  });
  if (wallets.isPending) return <Loading what={t("admin.user.loadingWallets")} />;
  if (wallets.error) return <ErrorAlert error={wallets.error} />;
  if (wallets.data.length === 0) return <Empty>{t("admin.user.noWallets")}</Empty>;
  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>{t("admin.user.card")}</th>
            <th>{t("admin.user.walletName")}</th>
            <th className="num">{t("admin.user.available")}</th>
            <th className="num">{t("admin.user.onHold")}</th>
            <th>{t("admin.user.state")}</th>
          </tr>
        </thead>
        <tbody>
          {wallets.data.map((wallet) => (
            <tr key={wallet.id}>
              <td data-label={t("admin.user.card")}>
                <span className="card-number">{formatCardNumber(wallet.card_number)}</span>
                <div className="muted small">
                  {wallet.currency} · <ShortId id={wallet.id} />
                </div>
              </td>
              <td data-label={t("admin.user.walletName")}>{wallet.name ?? "—"}</td>
              <td className="num" data-label={t("admin.user.available")}>
                <Money
                  minor={wallet.balance_minor - wallet.held_minor}
                  currency={wallet.currency}
                />
              </td>
              <td className="num" data-label={t("admin.user.onHold")}>
                <Money minor={wallet.held_minor} currency={wallet.currency} />
              </td>
              <td data-label={t("admin.user.state")}>
                <StatusBadge status={wallet.status} />
                {(wallet.is_primary || wallet.blocked) && (
                  <div className="muted small">
                    {[
                      wallet.is_primary && t("admin.user.main"),
                      wallet.blocked && t("admin.user.blockedByOwner"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">{t("admin.user.readOnly")}</p>
    </>
  );
}

function Operations({ userId }: { userId: string }) {
  const i18n = useI18n();
  const { t, maybe } = i18n;
  const operations = useQuery({
    queryKey: ["admin", "transactions", { user_id: userId }, "latest"],
    queryFn: () => api.adminListTransactions({ user_id: userId }, { limit: LATEST, offset: 0 }),
  });
  if (operations.isPending) return <Loading what={t("admin.user.loadingOperations")} />;
  if (operations.error) return <ErrorAlert error={operations.error} />;
  if (operations.data.length === 0) return <Empty>{t("admin.user.noOperations")}</Empty>;
  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>{t("admin.col.when")}</th>
            <th>{t("admin.col.reference")}</th>
            <th>{t("admin.col.status")}</th>
            <th className="num">{t("admin.col.amount")}</th>
          </tr>
        </thead>
        <tbody>
          {operations.data.map((item) => (
            <tr key={item.id}>
              <td data-label={t("admin.col.when")}>
                <DateTime value={item.created_at} />
              </td>
              <td data-label={t("admin.col.reference")}>
                {item.reference}
                <div className="muted small">
                  {maybe(`type.${item.type}`) ?? item.type}
                  {item.counterparty_name && ` → ${item.counterparty_name}`}
                </div>
              </td>
              <td data-label={t("admin.col.status")}>
                <StatusBadge status={item.status} />
                {item.failure_reason && (
                  <div className="muted small">{reasonText(item.failure_reason, i18n)}</div>
                )}
              </td>
              <td className="num" data-label={t("admin.col.amount")}>
                <Money minor={item.amount_minor} currency={item.currency} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <Link to={`/admin/transactions?user_id=${userId}`}>{t("admin.user.allOperations")}</Link>
      </p>
    </>
  );
}

function Support({ userId }: { userId: string }) {
  const { t } = useI18n();
  const thread = useQuery({
    queryKey: ["admin", "support", "thread", userId],
    queryFn: () => api.adminSupportThread(userId),
    retry: false,
  });
  if (thread.isPending) return <Loading what={t("admin.user.loading")} />;
  // 404: they have simply never written.
  if (thread.error instanceof ApiError && thread.error.status === 404) {
    return <Empty>{t("admin.user.noSupport")}</Empty>;
  }
  if (thread.error) return <ErrorAlert error={thread.error} />;
  return (
    <div className="card">
      <p>
        <StatusBadge status={thread.data.status} />{" "}
        <span className="muted small">
          <DateTime value={thread.data.last_message_at} />
        </span>
      </p>
      <p>
        <span className="muted">
          {t("admin.user.lastMessage", {
            sender:
              thread.data.last_sender === "STAFF"
                ? t("admin.user.fromStaff")
                : t("admin.user.fromCustomer"),
          })}
        </span>{" "}
        {thread.data.last_body}
      </p>
      <p>
        <Link to={`/admin/support?user=${userId}`}>{t("admin.user.openConversation")}</Link>
      </p>
    </div>
  );
}

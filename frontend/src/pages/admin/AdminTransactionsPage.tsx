import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
import { CustomerLink, CustomerName } from "../../components/admin/Customer";
import { DownloadButton } from "../../components/DownloadButton";
import { useI18n } from "../../i18n";
import { formatMinor } from "../../lib/money";
import { reasonText } from "../../lib/reasons";
import { DateTime, Empty, ErrorAlert, Loading, Money, Pager, ShortId, StatusBadge } from "../../components/ui";

const PAGE_SIZE = 50;
const STATUSES = [
  "PENDING",
  "CREATED",
  "PROCESSING",
  "COMPLETED",
  "SUCCESS",
  "FAILED",
  "EXPIRED",
  "CANCELLED",
  "PARTIALLY_REFUNDED",
  "REFUNDED",
];

export function AdminTransactionsPage() {
  // Filters live in the URL so a filtered view can be linked to (the
  // users page links here with ?user_id=).
  const i18n = useI18n();
  const { t, maybe } = i18n;
  const [params, setParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const filters: api.AdminTransactionFilters = {
    type: (params.get("type") as api.TransactionType | null) ?? undefined,
    status: params.get("status") ?? undefined,
    user_id: params.get("user_id") ?? undefined,
  };

  const transactions = useQuery({
    queryKey: ["admin", "transactions", filters, offset],
    queryFn: () => api.adminListTransactions(filters, { limit: PAGE_SIZE, offset }),
  });

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setOffset(0);
    setParams(next);
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("admin.tx.title")}</h1>
          <p className="muted">{t("admin.tx.subtitle")}</p>
        </div>
        <div className="inline-form">
          <select
            aria-label={t("admin.tx.type")}
            value={filters.type ?? ""}
            onChange={(e) => setFilter("type", e.target.value)}
          >
            <option value="">{t("admin.tx.allTypes")}</option>
            <option value="TRANSFER">{t("admin.tx.transfers")}</option>
            <option value="PAYMENT">{t("admin.tx.payments")}</option>
            <option value="EXCHANGE">{t("admin.tx.exchanges")}</option>
          </select>
          <select
            aria-label={t("admin.col.status")}
            value={filters.status ?? ""}
            onChange={(e) => setFilter("status", e.target.value)}
          >
            <option value="">{t("admin.tx.anyStatus")}</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {maybe(`status.${status}`) ?? status}
              </option>
            ))}
          </select>
          <input
            key={filters.user_id ?? ""}
            aria-label={t("admin.tx.userId")}
            placeholder={t("admin.tx.userIdPlaceholder")}
            defaultValue={filters.user_id ?? ""}
            onBlur={(e) => setFilter("user_id", e.target.value.trim())}
            onKeyDown={(e) => {
              if (e.key === "Enter") setFilter("user_id", e.currentTarget.value.trim());
            }}
          />
          {/* What is listed, under the same filters, as a file. */}
          <DownloadButton
            label={t("admin.tx.download")}
            fetchFile={() => api.adminDownloadTransactions(filters)}
          />
        </div>
      </header>
      <ErrorAlert error={transactions.error} />
      {transactions.isPending ? (
        <Loading what={t("admin.tx.loading")} />
      ) : transactions.data?.length === 0 && offset === 0 ? (
        <Empty>{t("admin.tx.empty")}</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("admin.col.when")}</th>
                <th>{t("admin.col.reference")}</th>
                <th>{t("admin.col.user")}</th>
                <th>{t("admin.col.status")}</th>
                <th>{t("admin.col.fraud")}</th>
                <th className="num">{t("admin.col.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data?.map((item) => (
                <tr key={item.id}>
                  <td data-label={t("admin.col.when")}>
                    <DateTime value={item.created_at} />
                  </td>
                  <td data-label={t("admin.col.reference")}>
                    {item.reference}
                    <div className="muted small">
                      {maybe(`type.${item.type}`) ?? item.type} →{" "}
                      {item.counterparty_name ?? <ShortId id={item.counterparty_id} />}
                    </div>
                  </td>
                  <td data-label={t("admin.col.user")}>
                    <CustomerLink userId={item.initiator_user_id} />
                  </td>
                  <td data-label={t("admin.col.status")}>
                    <StatusBadge status={item.status} />
                    {item.failure_reason && (
                      <div className="muted small">{reasonText(item.failure_reason, i18n)}</div>
                    )}
                  </td>
                  <td data-label={t("admin.col.fraud")}>
                    {item.fraud_decision ? <StatusBadge status={item.fraud_decision} /> : "—"}
                    {item.reviewed_by_user_id && (
                      <div className="muted small">
                        {t("admin.tx.reviewedBy")} <CustomerName userId={item.reviewed_by_user_id} />
                      </div>
                    )}
                  </td>
                  <td className="num" data-label={t("admin.col.amount")}>
                    <Money minor={item.amount_minor} currency={item.currency} />
                    {/* An exchange: what that amount was exchanged for. */}
                    {item.received_amount_minor != null && item.received_currency && (
                      <div className="muted small">
                        {t("admin.tx.received", {
                          amount: formatMinor(item.received_amount_minor, item.received_currency),
                        })}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={transactions.data?.length ?? 0}
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}

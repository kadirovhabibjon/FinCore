import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DownloadButton } from "../components/DownloadButton";
import { DateTime, Empty, ErrorAlert, Loading, Money, Pager, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { describe, sign } from "../lib/history";

const PAGE_SIZE = 25;

export function TransactionsPage() {
  const [offset, setOffset] = useState(0);
  const { t } = useI18n();
  const transactions = useQuery({
    queryKey: ["transactions", offset],
    queryFn: () => api.listTransactions({ limit: PAGE_SIZE, offset }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("history.title")}</h1>
          <p className="muted">{t("history.subtitle")}</p>
        </div>
        <div className="actions">
          <Link to="/stats" className="button button-ghost">
            {t("history.statistics")}
          </Link>
          <DownloadButton label={t("history.csv")} fetchFile={api.downloadStatement} />
        </div>
      </header>
      <ErrorAlert error={transactions.error} />
      {transactions.isPending ? (
        <Loading what={t("history.loading")} />
      ) : transactions.data?.length === 0 && offset === 0 ? (
        <Empty>{t("history.empty")}</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("history.when")}</th>
                <th>{t("history.reference")}</th>
                <th>{t("history.type")}</th>
                <th>{t("history.status")}</th>
                <th className="num">{t("history.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data?.map((item) => (
                <tr key={item.id}>
                  <td data-label={t("history.when")}>
                    <DateTime value={item.created_at} />
                  </td>
                  <td data-label={t("history.reference")}>
                    <Link to={`/transactions/${item.id}`}>{item.reference}</Link>
                    {item.description && <div className="muted small">{item.description}</div>}
                  </td>
                  <td data-label={t("history.type")}>
                    {t(describe(item))}
                    {item.counterparty_name && (
                      <div className="muted small">
                        {t(item.direction === "IN" ? "history.from" : "history.to", {
                          name: item.counterparty_name,
                        })}
                      </div>
                    )}
                  </td>
                  <td data-label={t("history.status")}>
                    <StatusBadge status={item.status} />
                  </td>
                  <td
                    className={item.direction === "IN" ? "num amount-in" : "num"}
                    data-label={t("history.amount")}
                  >
                    {sign(item)}
                    <Money minor={item.amount_minor} currency={item.currency} />
                    {item.received_amount_minor != null && item.received_currency && (
                      <div className="muted small">
                        → <Money minor={item.received_amount_minor} currency={item.received_currency} />
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

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { DownloadButton } from "../components/DownloadButton";
import { DateTime, Empty, ErrorAlert, Loading, Money, Pager, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { describe, sign } from "../lib/history";
import { useDebounced } from "../lib/useDebounced";

const PAGE_SIZE = 25;

// What "Show" offers, as the filter each choice stands for.
const KINDS = {
  "": {},
  received: { direction: "IN" },
  sent: { type: "TRANSFER", direction: "OUT" },
  payments: { type: "PAYMENT" },
  exchanges: { type: "EXCHANGE" },
} as const satisfies Record<string, api.HistoryFilter>;
type Kind = keyof typeof KINDS;

export function TransactionsPage() {
  const [offset, setOffset] = useState(0);
  const { t } = useI18n();
  // The filters live in the URL: a filtered view can be reloaded,
  // bookmarked and gone back to.
  const [params, setParams] = useSearchParams();
  const kind = (params.get("show") ?? "") as Kind;
  const dateFrom = params.get("from") ?? "";
  const dateTo = params.get("to") ?? "";
  const words = params.get("q") ?? "";
  // Typing searches once it pauses, not on every key.
  const [typed, setTyped] = useState(words);
  const settled = useDebounced(typed.trim(), 350);
  useEffect(() => {
    if (settled !== words) change("q", settled);
    // Only when the typing settles; `change` and `words` follow from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settled]);

  function change(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setOffset(0);
    setParams(next, { replace: true });
  }

  const filter: api.HistoryFilter = {
    ...KINDS[kind],
    q: words || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const filtered = !!(kind || words || dateFrom || dateTo);
  const transactions = useQuery({
    queryKey: ["transactions", filter, offset],
    queryFn: () => api.listTransactions({ limit: PAGE_SIZE, offset }, filter),
    // A changed filter keeps the old rows up while the new ones load.
    placeholderData: (previous) => previous,
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
          <DownloadButton
            label={filtered ? t("history.csvFiltered") : t("history.csv")}
            fetchFile={() => api.downloadStatement(filter)}
          />
        </div>
      </header>
      <div className="history-filters" role="search" aria-label={t("history.filters")}>
        <label>
          {t("history.search")}
          <input
            type="search"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={t("history.searchPlaceholder")}
            maxLength={64}
          />
        </label>
        <label>
          {t("history.kind")}
          <select value={kind} onChange={(event) => change("show", event.target.value)}>
            <option value="">{t("history.kindAll")}</option>
            <option value="received">{t("history.kindReceived")}</option>
            <option value="sent">{t("history.kindSent")}</option>
            <option value="payments">{t("history.kindPayments")}</option>
            <option value="exchanges">{t("history.kindExchanges")}</option>
          </select>
        </label>
        <label>
          {t("history.dateFrom")}
          <input
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(event) => change("from", event.target.value)}
          />
        </label>
        <label>
          {t("history.dateTo")}
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(event) => change("to", event.target.value)}
          />
        </label>
        {filtered && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              setTyped("");
              setOffset(0);
              setParams({}, { replace: true });
            }}
          >
            {t("history.clear")}
          </button>
        )}
      </div>
      <ErrorAlert error={transactions.error} />
      {transactions.isPending ? (
        <Loading what={t("history.loading")} />
      ) : transactions.data?.length === 0 && offset === 0 ? (
        <Empty>{filtered ? t("history.noMatch") : t("history.empty")}</Empty>
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

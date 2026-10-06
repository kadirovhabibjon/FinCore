import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { CardQr } from "../components/CardQr";
import {
  CopyButton,
  DateTime,
  Empty,
  ErrorAlert,
  Loading,
  Money,
  Pager,
  ShortId,
  StatusBadge,
} from "../components/ui";
import { formatCardNumber } from "../lib/card";
import { useI18n } from "../i18n";

const PAGE_SIZE = 25;

export function WalletPage() {
  const { walletId = "" } = useParams();
  const [offset, setOffset] = useState(0);
  const [showQr, setShowQr] = useState(false);
  const { t } = useI18n();
  const wallet = useQuery({ queryKey: ["wallet", walletId], queryFn: () => api.getWallet(walletId) });
  const entries = useQuery({
    queryKey: ["wallet", walletId, "entries", offset],
    queryFn: () => api.listWalletEntries(walletId, { limit: PAGE_SIZE, offset }),
  });

  if (wallet.isPending) return <Loading what={t("wallet.loading")} />;
  if (wallet.error) return <ErrorAlert error={wallet.error} />;
  const { currency } = wallet.data;

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>
            {t("wallet.name", { currency })} <ShortId id={wallet.data.id} />
          </h1>
          <p className="muted">
            {t("wallet.cardNumber")}{" "}
            <strong className="card-number">{formatCardNumber(wallet.data.card_number)}</strong>{" "}
            <CopyButton text={wallet.data.card_number} label={t("wallet.copyNumber")} />
            <br />
            {t("wallet.share")}
          </p>
        </div>
        <Link to={`/transfer?from=${wallet.data.id}`} className="button">
          {t("wallet.sendFrom")}
        </Link>
      </header>

      <div className="receive">
        <button
          type="button"
          className="button button-ghost"
          aria-expanded={showQr}
          onClick={() => setShowQr((shown) => !shown)}
        >
          {showQr ? t("wallet.hideQr") : t("wallet.showQr")}
        </button>
        {showQr && <CardQr cardNumber={wallet.data.card_number} />}
      </div>

      <div className="stats">
        <div className="card stat">
          <span className="muted small">{t("wallet.available")}</span>
          <Money minor={wallet.data.balance_minor - wallet.data.held_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">{t("wallet.onHold")}</span>
          <Money minor={wallet.data.held_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">{t("wallet.ledgerBalance")}</span>
          <Money minor={wallet.data.balance_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">{t("wallet.status")}</span>
          <StatusBadge status={wallet.data.status} />
        </div>
      </div>

      <h2>{t("wallet.entries")}</h2>
      <ErrorAlert error={entries.error} />
      {entries.isPending ? (
        <Loading what={t("wallet.loadingEntries")} />
      ) : entries.data?.length === 0 && offset === 0 ? (
        <Empty>{t("wallet.noEntries")}</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("wallet.when")}</th>
                <th>{t("wallet.posting")}</th>
                <th className="num">{t("wallet.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.data?.map((entry) => (
                <tr key={entry.id}>
                  <td data-label={t("wallet.when")}>
                    <DateTime value={entry.created_at} />
                  </td>
                  <td data-label={t("wallet.posting")}>
                    <ShortId id={entry.posting_id} />
                  </td>
                  <td className={`num ${entry.direction === "CREDIT" ? "credit" : "debit"}`} data-label={t("wallet.amount")}>
                    {entry.direction === "CREDIT" ? "+" : "−"}
                    <Money minor={entry.amount_minor} currency={entry.currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={entries.data?.length ?? 0}
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}

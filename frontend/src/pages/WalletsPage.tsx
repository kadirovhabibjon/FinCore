import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ExchangeRates } from "../components/ExchangeRates";
import { Empty, ErrorAlert, Loading, Money, ShortId, StatusBadge } from "../components/ui";
import { formatCardNumber } from "../lib/card";
import { SUPPORTED_CURRENCIES } from "../lib/money";
import { useI18n } from "../i18n";

export function WalletsPage() {
  const { user } = useAuth();
  const { t, tr } = useI18n();
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [currency, setCurrency] = useState(SUPPORTED_CURRENCIES[0] ?? "UZS");
  // Failing quietly: the wallets matter more than this shortcut.
  const requests = useQuery({
    queryKey: ["money-requests"],
    queryFn: api.listMoneyRequests,
    retry: false,
  });
  const waiting =
    requests.data?.filter((item) => item.direction === "INCOMING" && item.status === "PENDING")
      .length ?? 0;
  const create = useMutation({
    mutationFn: api.createWallet,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["wallets"] }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("wallets.hello", { name: user?.first_name ?? "" })}</h1>
          <p className="muted">{t("wallets.subtitle")}</p>
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(currency);
          }}
        >
          <select
            aria-label={t("wallets.currency")}
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {SUPPORTED_CURRENCIES.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </select>
          <button type="submit" className="button" disabled={create.isPending}>
            {t("wallets.new")}
          </button>
        </form>
      </header>
      <ErrorAlert error={create.error ?? wallets.error} />
      <p className="requests-bar">
        {waiting > 0 ? (
          <Link to="/requests" className="requests-waiting">
            {waiting === 1
              ? t("wallets.oneAsking")
              : t("wallets.manyAsking", { count: waiting })}{" "}
            →
          </Link>
        ) : (
          <Link to="/requests">{t("wallets.request")}</Link>
        )}
        {(wallets.data?.length ?? 0) > 1 && (
          <Link to="/exchange" className="requests-bar-link">
            {t("wallets.exchange")}
          </Link>
        )}
      </p>
      {wallets.isPending ? (
        <Loading what={t("wallets.loading")} />
      ) : wallets.data?.length === 0 ? (
        <Empty>{t("wallets.empty")}</Empty>
      ) : (
        <div className="grid">
          {wallets.data?.map((wallet) => (
            <Link key={wallet.id} to={`/wallets/${wallet.id}`} className="card wallet-card">
              <div className="wallet-card-head">
                <span className="muted">
                  {wallet.name ?? t("wallet.name", { currency: wallet.currency })}{" "}
                  <ShortId id={wallet.id} />
                </span>
                <span className="wallet-flags">
                  {wallet.is_primary && <span className="badge">{t("card.main")}</span>}
                  {wallet.blocked ? (
                    <span className="badge badge-bad">{t("card.blocked")}</span>
                  ) : (
                    <StatusBadge status={wallet.status} />
                  )}
                </span>
              </div>
              <div className="card-number" aria-label={t("wallet.cardNumber")}>
                {formatCardNumber(wallet.card_number)}
              </div>
              <div className="wallet-balance">
                <Money minor={wallet.balance_minor - wallet.held_minor} currency={wallet.currency} />
              </div>
              <div className="muted small">
                {t("wallets.available")}
                {wallet.held_minor > 0 && (
                  <>
                    {" "}
                    ·{" "}
                    {tr("wallets.onHold", {
                      amount: <Money minor={wallet.held_minor} currency={wallet.currency} />,
                    })}
                  </>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
      <ExchangeRates />
    </section>
  );
}

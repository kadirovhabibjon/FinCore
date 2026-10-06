import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ExchangeRates } from "../components/ExchangeRates";
import { Empty, ErrorAlert, Loading, Money, ShortId, StatusBadge } from "../components/ui";
import { formatCardNumber } from "../lib/card";
import { SUPPORTED_CURRENCIES } from "../lib/money";

export function WalletsPage() {
  const { user } = useAuth();
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
          <h1>Hello, {user?.first_name}</h1>
          <p className="muted">Your wallets and balances.</p>
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(currency);
          }}
        >
          <select
            aria-label="Wallet currency"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {SUPPORTED_CURRENCIES.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </select>
          <button type="submit" className="button" disabled={create.isPending}>
            New wallet
          </button>
        </form>
      </header>
      <ErrorAlert error={create.error ?? wallets.error} />
      <p className="requests-bar">
        {waiting > 0 ? (
          <Link to="/requests" className="requests-waiting">
            {waiting === 1
              ? "1 person is asking you for money"
              : `${waiting} people are asking you for money`}{" "}
            →
          </Link>
        ) : (
          <Link to="/requests">Request money from someone →</Link>
        )}
        {(wallets.data?.length ?? 0) > 1 && (
          <Link to="/exchange" className="requests-bar-link">
            Exchange between your wallets →
          </Link>
        )}
      </p>
      {wallets.isPending ? (
        <Loading what="Loading wallets" />
      ) : wallets.data?.length === 0 ? (
        <Empty>You have no wallets yet. Create one to receive and send money.</Empty>
      ) : (
        <div className="grid">
          {wallets.data?.map((wallet) => (
            <Link key={wallet.id} to={`/wallets/${wallet.id}`} className="card wallet-card">
              <div className="wallet-card-head">
                <span className="muted">
                  {wallet.currency} wallet <ShortId id={wallet.id} />
                </span>
                <StatusBadge status={wallet.status} />
              </div>
              <div className="card-number" aria-label="Card number">
                {formatCardNumber(wallet.card_number)}
              </div>
              <div className="wallet-balance">
                <Money minor={wallet.balance_minor - wallet.held_minor} currency={wallet.currency} />
              </div>
              <div className="muted small">
                available
                {wallet.held_minor > 0 && (
                  <>
                    {" "}
                    · <Money minor={wallet.held_minor} currency={wallet.currency} /> on hold
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

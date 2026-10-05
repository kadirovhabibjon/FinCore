import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import * as api from "../api/endpoints";
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

const PAGE_SIZE = 25;

export function WalletPage() {
  const { walletId = "" } = useParams();
  const [offset, setOffset] = useState(0);
  const wallet = useQuery({ queryKey: ["wallet", walletId], queryFn: () => api.getWallet(walletId) });
  const entries = useQuery({
    queryKey: ["wallet", walletId, "entries", offset],
    queryFn: () => api.listWalletEntries(walletId, { limit: PAGE_SIZE, offset }),
  });

  if (wallet.isPending) return <Loading what="Loading wallet" />;
  if (wallet.error) return <ErrorAlert error={wallet.error} />;
  const { currency } = wallet.data;

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>
            {currency} wallet <ShortId id={wallet.data.id} />
          </h1>
          <p className="muted">
            Card number{" "}
            <strong className="card-number">{formatCardNumber(wallet.data.card_number)}</strong>{" "}
            <CopyButton text={wallet.data.card_number} label="Copy number" />
            <br />
            Share it to receive transfers: the sender types it on the Send page.
          </p>
        </div>
        <Link to={`/transfer?from=${wallet.data.id}`} className="button">
          Send from this wallet
        </Link>
      </header>

      <div className="stats">
        <div className="card stat">
          <span className="muted small">Available</span>
          <Money minor={wallet.data.balance_minor - wallet.data.held_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">On hold</span>
          <Money minor={wallet.data.held_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">Ledger balance</span>
          <Money minor={wallet.data.balance_minor} currency={currency} />
        </div>
        <div className="card stat">
          <span className="muted small">Status</span>
          <StatusBadge status={wallet.data.status} />
        </div>
      </div>

      <h2>Ledger entries</h2>
      <ErrorAlert error={entries.error} />
      {entries.isPending ? (
        <Loading what="Loading entries" />
      ) : entries.data?.length === 0 && offset === 0 ? (
        <Empty>No money has moved through this wallet yet.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Posting</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {entries.data?.map((entry) => (
                <tr key={entry.id}>
                  <td data-label="When">
                    <DateTime value={entry.created_at} />
                  </td>
                  <td data-label="Posting">
                    <ShortId id={entry.posting_id} />
                  </td>
                  <td className={`num ${entry.direction === "CREDIT" ? "credit" : "debit"}`} data-label="Amount">
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

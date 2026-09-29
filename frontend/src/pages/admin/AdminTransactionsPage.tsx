import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
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
          <h1>All transactions</h1>
          <p className="muted">Every user&apos;s transfers and payments, newest first.</p>
        </div>
        <div className="inline-form">
          <select
            aria-label="Type"
            value={filters.type ?? ""}
            onChange={(e) => setFilter("type", e.target.value)}
          >
            <option value="">All types</option>
            <option value="TRANSFER">Transfers</option>
            <option value="PAYMENT">Payments</option>
          </select>
          <select
            aria-label="Status"
            value={filters.status ?? ""}
            onChange={(e) => setFilter("status", e.target.value)}
          >
            <option value="">Any status</option>
            {STATUSES.map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
          <input
            key={filters.user_id ?? ""}
            aria-label="User id"
            placeholder="user id"
            defaultValue={filters.user_id ?? ""}
            onBlur={(e) => setFilter("user_id", e.target.value.trim())}
            onKeyDown={(e) => {
              if (e.key === "Enter") setFilter("user_id", e.currentTarget.value.trim());
            }}
          />
        </div>
      </header>
      <ErrorAlert error={transactions.error} />
      {transactions.isPending ? (
        <Loading what="Loading transactions" />
      ) : transactions.data?.length === 0 && offset === 0 ? (
        <Empty>No transactions match.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Reference</th>
                <th>User</th>
                <th>Status</th>
                <th>Fraud</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data?.map((item) => (
                <tr key={item.id}>
                  <td>
                    <DateTime value={item.created_at} />
                  </td>
                  <td>
                    {item.reference}
                    <div className="muted small">
                      {item.type} → <ShortId id={item.counterparty_id} />
                    </div>
                  </td>
                  <td>
                    <ShortId id={item.initiator_user_id} />
                  </td>
                  <td>
                    <StatusBadge status={item.status} />
                    {item.failure_reason && (
                      <div className="muted small">{item.failure_reason}</div>
                    )}
                  </td>
                  <td>
                    {item.fraud_decision ? <StatusBadge status={item.fraud_decision} /> : "—"}
                    {item.reviewed_by_user_id && (
                      <div className="muted small">
                        reviewed by <ShortId id={item.reviewed_by_user_id} />
                      </div>
                    )}
                  </td>
                  <td className="num">
                    <Money minor={item.amount_minor} currency={item.currency} />
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

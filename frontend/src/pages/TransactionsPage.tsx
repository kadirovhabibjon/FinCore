import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, Money, Pager, StatusBadge } from "../components/ui";

const PAGE_SIZE = 25;

export function TransactionsPage() {
  const [offset, setOffset] = useState(0);
  const transactions = useQuery({
    queryKey: ["transactions", offset],
    queryFn: () => api.listTransactions({ limit: PAGE_SIZE, offset }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>History</h1>
          <p className="muted">
            Transfers and payments you started. Money you received shows on the wallet itself.
          </p>
        </div>
      </header>
      <ErrorAlert error={transactions.error} />
      {transactions.isPending ? (
        <Loading what="Loading history" />
      ) : transactions.data?.length === 0 && offset === 0 ? (
        <Empty>Nothing here yet.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Reference</th>
                <th>Type</th>
                <th>Status</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data?.map((item) => (
                <tr key={item.id}>
                  <td data-label="When">
                    <DateTime value={item.created_at} />
                  </td>
                  <td data-label="Reference">
                    <Link to={`/transactions/${item.id}`}>{item.reference}</Link>
                    {item.description && <div className="muted small">{item.description}</div>}
                  </td>
                  <td data-label="Type">{item.type}</td>
                  <td data-label="Status">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="num" data-label="Amount">
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

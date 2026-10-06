import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, Money, Pager, StatusBadge } from "../components/ui";

const PAGE_SIZE = 25;

function describe(item: api.Transaction): string {
  if (item.type === "PAYMENT") return "Payment";
  if (item.type === "EXCHANGE") return "Exchanged";
  return item.direction === "IN" ? "Received" : "Sent";
}

const NOT_MOVED = new Set(["FAILED", "EXPIRED", "CANCELLED"]);

/** "+" for money in, "−" for money out, nothing when none moved. */
function sign(item: api.Transaction): string {
  // An exchange is the customer's own money changing currency: neither in nor out.
  if (NOT_MOVED.has(item.status) || item.direction === "SELF") return "";
  return item.direction === "IN" ? "+" : "−";
}

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
            Money you sent, paid and received, newest first.
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
                  <td data-label="Type">
                    {describe(item)}
                    {item.counterparty_name && (
                      <div className="muted small">
                        {item.direction === "IN" ? "from" : "to"} {item.counterparty_name}
                      </div>
                    )}
                  </td>
                  <td data-label="Status">
                    <StatusBadge status={item.status} />
                  </td>
                  <td
                    className={item.direction === "IN" ? "num amount-in" : "num"}
                    data-label="Amount"
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

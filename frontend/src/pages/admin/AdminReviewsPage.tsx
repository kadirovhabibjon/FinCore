import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { DateTime, Empty, ErrorAlert, Loading, Money, Notice, ShortId, StatusBadge } from "../../components/ui";

export function AdminReviewsPage() {
  const { user } = useAuth();
  const isAdmin = hasAnyRole(user, "ADMIN");
  const queryClient = useQueryClient();
  const [lastDecision, setLastDecision] = useState<api.AdminTransaction | null>(null);

  const reviews = useQuery({
    queryKey: ["admin", "reviews"],
    queryFn: api.adminListReviews,
    refetchInterval: 15_000,
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: api.ReviewDecision }) =>
      api.adminDecideReview(id, decision),
    onSuccess: (result) => setLastDecision(result),
    // A 409 means someone else (or the payment expiry) got there first:
    // refresh either way so the queue shows what is actually left.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "reviews"] }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Fraud review queue</h1>
          <p className="muted">
            Operations the fraud check flagged for a human decision, oldest first. Approving runs
            the rest of the operation immediately; rejecting fails it. Payments still here after
            15 minutes expire on their own.
          </p>
        </div>
      </header>
      {lastDecision && (
        <Notice>
          {lastDecision.reference} is now <StatusBadge status={lastDecision.status} />
          {lastDecision.failure_reason && ` — ${lastDecision.failure_reason}`}
        </Notice>
      )}
      <ErrorAlert error={reviews.error ?? decide.error} />
      {reviews.isPending ? (
        <Loading what="Loading queue" />
      ) : reviews.data?.length === 0 ? (
        <Empty>Nothing is waiting for review.</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Waiting since</th>
              <th>Reference</th>
              <th>Customer</th>
              <th>Destination</th>
              <th className="num">Amount</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {reviews.data?.map((item) => (
              <tr key={item.id}>
                <td data-label="Waiting since">
                  <DateTime value={item.created_at} />
                </td>
                <td data-label="Reference">
                  {item.reference}
                  <div className="muted small">{item.type}</div>
                </td>
                <td data-label="Customer">
                  <ShortId id={item.initiator_user_id} />
                </td>
                <td data-label="Destination">
                  <span className="muted small">{item.type === "TRANSFER" ? "wallet" : "merchant"}</span>{" "}
                  <ShortId id={item.counterparty_id} />
                </td>
                <td className="num" data-label="Amount">
                  <Money minor={item.amount_minor} currency={item.currency} />
                </td>
                <td className="num" data-label="">
                  {isAdmin ? (
                    <div className="actions">
                      <button
                        type="button"
                        className="button button-small"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: item.id, decision: "APPROVE" })}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="button button-small button-danger"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: item.id, decision: "REJECT" })}
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <span className="muted small">ADMIN decides</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { OperationOutcome } from "../components/OperationOutcome";
import { DateTime, ErrorAlert, Loading, Money, StatusBadge } from "../components/ui";

export function TransactionPage() {
  const { transactionId = "" } = useParams();
  const summary = useQuery({
    queryKey: ["transactions", "detail", transactionId],
    queryFn: () => api.getTransaction(transactionId),
  });
  const type = summary.data?.type;
  // The type-specific resource adds what the summary leaves out
  // (wallets, merchant, fraud decision, failure reason).
  const transfer = useQuery({
    queryKey: ["transfer", transactionId],
    queryFn: () => api.getTransfer(transactionId),
    enabled: type === "TRANSFER",
  });
  const payment = useQuery({
    queryKey: ["payment", transactionId],
    queryFn: () => api.getPayment(transactionId),
    enabled: type === "PAYMENT",
  });

  if (summary.isPending) return <Loading what="Loading transaction" />;
  if (summary.error) return <ErrorAlert error={summary.error} />;
  const detail = transfer.data ?? payment.data;
  const item = summary.data;

  return (
    <section className="page narrow">
      <h1>{item.type === "TRANSFER" ? "Transfer" : "Payment"}</h1>
      <OperationOutcome
        kind={item.type === "TRANSFER" ? "Transfer" : "Payment"}
        status={item.status}
        failureReason={detail?.failure_reason}
        reference={item.reference}
        amount={<Money minor={item.amount_minor} currency={item.currency} />}
      />
      <ErrorAlert error={transfer.error ?? payment.error} />
      <dl className="card details">
        <dt>Created</dt>
        <dd>
          <DateTime value={item.created_at} />
        </dd>
        <dt>Completed</dt>
        <dd>
          <DateTime value={item.completed_at} />
        </dd>
        {item.description && (
          <>
            <dt>Note</dt>
            <dd>{item.description}</dd>
          </>
        )}
        {transfer.data && (
          <>
            <dt>From wallet</dt>
            <dd>
              <code>{transfer.data.source_wallet_id}</code>
            </dd>
            <dt>To wallet</dt>
            <dd>
              <code>{transfer.data.destination_wallet_id}</code>
            </dd>
          </>
        )}
        {payment.data && (
          <>
            <dt>From wallet</dt>
            <dd>
              <code>{payment.data.source_wallet_id}</code>
            </dd>
            <dt>Merchant</dt>
            <dd>
              <code>{payment.data.merchant_id}</code>
            </dd>
            <dt>Refunded</dt>
            <dd>
              <Money minor={payment.data.refunded_amount_minor} currency={payment.data.currency} />
            </dd>
          </>
        )}
        {detail?.fraud_decision && (
          <>
            <dt>Fraud check</dt>
            <dd>
              <StatusBadge status={detail.fraud_decision} />
            </dd>
          </>
        )}
        <dt>Id</dt>
        <dd>
          <code>{item.id}</code>
        </dd>
      </dl>
    </section>
  );
}

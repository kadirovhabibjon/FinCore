import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { DownloadButton } from "../components/DownloadButton";
import { OperationOutcome } from "../components/OperationOutcome";
import { DateTime, ErrorAlert, Loading, Money, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";

export function TransactionPage() {
  const { transactionId = "" } = useParams();
  const { t } = useI18n();
  const summary = useQuery({
    queryKey: ["transactions", "detail", transactionId],
    queryFn: () => api.getTransaction(transactionId),
  });
  const type = summary.data?.type;
  // A transfer someone else sent: the summary is all the recipient may
  // see (the sender's wallets and fraud checks are the sender's).
  const incoming = summary.data?.direction === "IN";
  // The type-specific resource adds what the summary leaves out
  // (wallets, merchant, fraud decision, failure reason).
  const transfer = useQuery({
    queryKey: ["transfer", transactionId],
    queryFn: () => api.getTransfer(transactionId),
    enabled: type === "TRANSFER" && !incoming,
  });
  const payment = useQuery({
    queryKey: ["payment", transactionId],
    queryFn: () => api.getPayment(transactionId),
    enabled: type === "PAYMENT",
  });

  if (summary.isPending) return <Loading what={t("tx.loading")} />;
  if (summary.error) return <ErrorAlert error={summary.error} />;
  const detail = transfer.data ?? payment.data;
  const kind = t(
    summary.data.type === "TRANSFER"
      ? "kind.transfer"
      : summary.data.type === "EXCHANGE"
        ? "kind.exchange"
        : "kind.payment",
  );
  const title = incoming ? t("kind.received") : kind;
  const item = summary.data;

  return (
    <section className="page narrow">
      <h1>{title}</h1>
      <OperationOutcome
        kind={kind}
        status={item.status}
        failureReason={detail?.failure_reason}
        reference={item.reference}
        amount={<Money minor={item.amount_minor} currency={item.currency} />}
      />
      <ErrorAlert error={transfer.error ?? payment.error} />
      <div className="actions receipt-actions">
        <DownloadButton
          label={t("tx.receipt")}
          fetchFile={() => api.downloadReceipt(item.id)}
        />
      </div>
      <dl className="card details">
        {item.counterparty_name && (
          <>
            <dt>{incoming ? t("tx.from") : t("tx.to")}</dt>
            <dd>{item.counterparty_name}</dd>
          </>
        )}
        {item.received_amount_minor != null && item.received_currency && (
          <>
            <dt>{t("tx.exchangedFor")}</dt>
            <dd>
              <Money minor={item.received_amount_minor} currency={item.received_currency} />
            </dd>
          </>
        )}
        <dt>{t("tx.created")}</dt>
        <dd>
          <DateTime value={item.created_at} />
        </dd>
        <dt>{t("tx.completed")}</dt>
        <dd>
          <DateTime value={item.completed_at} />
        </dd>
        {item.description && (
          <>
            <dt>{t("tx.note")}</dt>
            <dd>{item.description}</dd>
          </>
        )}
        {transfer.data && (
          <>
            <dt>{t("tx.fromWallet")}</dt>
            <dd>
              <code>{transfer.data.source_wallet_id}</code>
            </dd>
            <dt>{t("tx.toWallet")}</dt>
            <dd>
              <code>{transfer.data.destination_wallet_id}</code>
            </dd>
          </>
        )}
        {payment.data && (
          <>
            <dt>{t("tx.fromWallet")}</dt>
            <dd>
              <code>{payment.data.source_wallet_id}</code>
            </dd>
            <dt>{t("tx.merchant")}</dt>
            <dd>
              <code>{payment.data.merchant_id}</code>
            </dd>
            <dt>{t("tx.refunded")}</dt>
            <dd>
              <Money minor={payment.data.refunded_amount_minor} currency={payment.data.currency} />
            </dd>
          </>
        )}
        {detail?.fraud_decision && (
          <>
            <dt>{t("tx.fraud")}</dt>
            <dd>
              <StatusBadge status={detail.fraud_decision} />
            </dd>
          </>
        )}
        <dt>{t("tx.id")}</dt>
        <dd>
          <code>{item.id}</code>
        </dd>
      </dl>
    </section>
  );
}

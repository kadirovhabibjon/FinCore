import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { DeliveriesTable } from "../components/DeliveriesTable";
import {
  CopyButton,
  DateTime,
  Empty,
  ErrorAlert,
  Loading,
  Money,
  Notice,
  Pager,
  StatusBadge,
} from "../components/ui";
import { validateAmount } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";
import { useI18n } from "../i18n";
import { reasonText } from "../lib/reasons";

const PAGE_SIZE = 20;
const REFUNDABLE = new Set(["SUCCESS", "PARTIALLY_REFUNDED"]);

export function MerchantPage() {
  const { merchantId = "" } = useParams();
  const { t, tr } = useI18n();
  const merchant = useQuery({
    queryKey: ["merchant", merchantId],
    queryFn: () => api.getMerchant(merchantId),
  });

  if (merchant.isPending) return <Loading what={t("merchant.loading")} />;
  if (merchant.error) return <ErrorAlert error={merchant.error} />;

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{merchant.data.name}</h1>
          <p className="muted">
            {tr("merchant.idLine", {
              id: <code>{merchant.data.id}</code>,
              copy: <CopyButton text={merchant.data.id} />,
            })}
          </p>
        </div>
        <StatusBadge status={merchant.data.status} />
      </header>
      <ReceivedPayments merchantId={merchantId} />
      <WebhookEndpoints merchantId={merchantId} />
    </section>
  );
}

function ReceivedPayments({ merchantId }: { merchantId: string }) {
  const { t } = useI18n();
  const [offset, setOffset] = useState(0);
  const [refunding, setRefunding] = useState<api.PaymentRecord | null>(null);
  const payments = useQuery({
    queryKey: ["merchant", merchantId, "payments", offset],
    queryFn: () => api.listMerchantPayments(merchantId, { limit: PAGE_SIZE, offset }),
  });

  return (
    <>
      <h2>{t("merchant.payments")}</h2>
      <ErrorAlert error={payments.error} />
      {refunding && (
        <RefundForm
          payment={refunding}
          merchantId={merchantId}
          onDone={() => setRefunding(null)}
        />
      )}
      {payments.isPending ? (
        <Loading what={t("merchant.loadingPayments")} />
      ) : payments.data?.length === 0 && offset === 0 ? (
        <Empty>{t("merchant.noPayments")}</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("history.when")}</th>
                <th>{t("history.reference")}</th>
                <th>{t("history.status")}</th>
                <th className="num">{t("history.amount")}</th>
                <th className="num">{t("merchant.refunded")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payments.data?.map((payment) => (
                <tr key={payment.id}>
                  <td data-label={t("history.when")}>
                    <DateTime value={payment.created_at} />
                  </td>
                  <td data-label={t("history.reference")}>{payment.reference}</td>
                  <td data-label={t("history.status")}>
                    <StatusBadge status={payment.status} />
                  </td>
                  <td className="num" data-label={t("history.amount")}>
                    <Money minor={payment.amount_minor} currency={payment.currency} />
                  </td>
                  <td className="num" data-label={t("merchant.refunded")}>
                    <Money minor={payment.refunded_amount_minor} currency={payment.currency} />
                  </td>
                  <td className="num" data-label="">
                    {REFUNDABLE.has(payment.status) && (
                      <button
                        type="button"
                        className="button button-small button-ghost"
                        onClick={() => setRefunding(payment)}
                      >
                        {t("merchant.refund")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={payments.data?.length ?? 0}
            onChange={setOffset}
          />
        </>
      )}
    </>
  );
}

function RefundForm({
  payment,
  merchantId,
  onDone,
}: {
  payment: api.PaymentRecord;
  merchantId: string;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const i18n = useI18n();
  const { t, tr } = i18n;
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();
  const remaining = payment.amount_minor - payment.refunded_amount_minor;

  const refund = useMutation({
    mutationFn: () =>
      api.createRefund(
        payment.id,
        { amount: amount.trim(), reason: reason.trim() || null },
        idempotencyKey,
      ),
    onSuccess: () => {
      renewKey();
      void queryClient.invalidateQueries({ queryKey: ["merchant", merchantId, "payments"] });
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateAmount(amount, payment.currency);
    setAmountError(problem);
    if (!problem) refund.mutate();
  }

  if (refund.isSuccess) {
    return (
      <Notice>
        {tr("merchant.refundDone", {
          amount: <Money minor={refund.data.amount_minor} currency={payment.currency} />,
          reference: payment.reference,
          status: <StatusBadge status={refund.data.status} />,
          reason: reasonText(refund.data.failure_reason ?? "", i18n),
        })}{" "}
        <button type="button" className="button button-small button-ghost" onClick={onDone}>
          {t("merchant.close")}
        </button>
      </Notice>
    );
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h3>
        {tr("merchant.refundTitle", {
          reference: payment.reference,
          amount: <Money minor={remaining} currency={payment.currency} />,
        })}
      </h3>
      <ErrorAlert error={refund.error} />
      <div className="row">
        <label>
          {t("send.amount", { currency: payment.currency })}
          <input
            value={amount}
            onChange={(e) => {
              setAmount(e.target.value);
              if (refund.isError) renewKey();
            }}
            inputMode="decimal"
            required
            aria-invalid={!!amountError}
          />
          {amountError && <span className="field-error">{amountError}</span>}
        </label>
        <label>
          {t("merchant.reason")}
          <input
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (refund.isError) renewKey();
            }}
            maxLength={255}
          />
        </label>
      </div>
      <div className="actions">
        <button type="button" className="button button-ghost" onClick={onDone}>
          {t("merchant.cancel")}
        </button>
        <button type="submit" className="button" disabled={refund.isPending}>
          {refund.isPending ? t("merchant.refunding") : t("merchant.refund")}
        </button>
      </div>
    </form>
  );
}

function WebhookEndpoints({ merchantId }: { merchantId: string }) {
  const queryClient = useQueryClient();
  const { t, tr } = useI18n();
  const endpoints = useQuery({ queryKey: ["webhooks"], queryFn: api.listWebhookEndpoints });
  const [url, setUrl] = useState("");
  const [revealed, setRevealed] = useState<api.WebhookEndpointWithSecret | null>(null);
  const [openEndpoint, setOpenEndpoint] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["webhooks"] });

  const create = useMutation({
    mutationFn: () => api.createWebhookEndpoint(merchantId, url.trim()),
    onSuccess: (endpoint) => {
      setUrl("");
      setRevealed(endpoint);
      void refresh();
    },
  });
  const rotate = useMutation({
    mutationFn: api.rotateWebhookSecret,
    onSuccess: (endpoint) => {
      setRevealed(endpoint);
      void refresh();
    },
  });
  const enable = useMutation({ mutationFn: api.enableWebhookEndpoint, onSuccess: refresh });

  const mine = endpoints.data?.filter((endpoint) => endpoint.merchant_id === merchantId) ?? [];

  return (
    <>
      <h2>{t("merchant.webhooks")}</h2>
      <p className="muted">
        {t("merchant.webhooksIntro")}
      </p>
      {revealed && (
        <div className="alert alert-warn" role="status">
          <strong>{t("merchant.secretFor", { url: revealed.url })}</strong>
          <p>{t("merchant.saveNow")}</p>
          <code className="secret">{revealed.secret}</code> <CopyButton text={revealed.secret} />{" "}
          <button
            type="button"
            className="button button-small button-ghost"
            onClick={() => setRevealed(null)}
          >
            {t("merchant.saved")}
          </button>
        </div>
      )}
      <ErrorAlert error={create.error ?? rotate.error ?? enable.error ?? endpoints.error} />
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input
          aria-label={t("merchant.webhookUrl")}
          type="url"
          placeholder="https://example.com/fincore-webhooks"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          maxLength={2048}
        />
        <button type="submit" className="button" disabled={create.isPending}>
          {t("merchant.addEndpoint")}
        </button>
      </form>
      {endpoints.isPending ? (
        <Loading what={t("merchant.loadingEndpoints")} />
      ) : mine.length === 0 ? (
        <Empty>{t("merchant.noEndpoints")}</Empty>
      ) : (
        <ul className="list">
          {mine.map((endpoint) => (
            <li key={endpoint.id} className="card">
              <div className="list-row">
                <div>
                  <code>{endpoint.url}</code>
                  <div className="muted small">
                    {tr("merchant.failures", {
                      count: endpoint.consecutive_failures,
                      when: <DateTime value={endpoint.created_at} />,
                    })}
                  </div>
                </div>
                <div className="actions">
                  <StatusBadge status={endpoint.status} />
                  {endpoint.status !== "ACTIVE" && (
                    <button
                      type="button"
                      className="button button-small"
                      onClick={() => enable.mutate(endpoint.id)}
                    >
                      {t("merchant.enable")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="button button-small button-ghost"
                    onClick={() => rotate.mutate(endpoint.id)}
                  >
                    {t("merchant.rotate")}
                  </button>
                  <button
                    type="button"
                    className="button button-small button-ghost"
                    onClick={() =>
                      setOpenEndpoint(openEndpoint === endpoint.id ? null : endpoint.id)
                    }
                  >
                    {openEndpoint === endpoint.id
                      ? t("merchant.hideDeliveries")
                      : t("merchant.deliveries")}
                  </button>
                </div>
              </div>
              {openEndpoint === endpoint.id && <EndpointDeliveries endpointId={endpoint.id} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function EndpointDeliveries({ endpointId }: { endpointId: string }) {
  const { t } = useI18n();
  const [offset, setOffset] = useState(0);
  const deliveries = useQuery({
    queryKey: ["webhooks", endpointId, "deliveries", offset],
    queryFn: () => api.listWebhookDeliveries(endpointId, { limit: PAGE_SIZE, offset }),
  });
  if (deliveries.isPending) return <Loading what={t("merchant.loadingDeliveries")} />;
  if (deliveries.error) return <ErrorAlert error={deliveries.error} />;
  return (
    <>
      <DeliveriesTable deliveries={deliveries.data} />
      <Pager offset={offset} limit={PAGE_SIZE} count={deliveries.data.length} onChange={setOffset} />
    </>
  );
}

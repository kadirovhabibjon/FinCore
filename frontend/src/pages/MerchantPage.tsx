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

const PAGE_SIZE = 20;
const REFUNDABLE = new Set(["SUCCESS", "PARTIALLY_REFUNDED"]);

export function MerchantPage() {
  const { merchantId = "" } = useParams();
  const merchant = useQuery({
    queryKey: ["merchant", merchantId],
    queryFn: () => api.getMerchant(merchantId),
  });

  if (merchant.isPending) return <Loading what="Loading merchant" />;
  if (merchant.error) return <ErrorAlert error={merchant.error} />;

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{merchant.data.name}</h1>
          <p className="muted">
            Merchant id <code>{merchant.data.id}</code> <CopyButton text={merchant.data.id} /> —
            customers pay you with this id.
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
  const [offset, setOffset] = useState(0);
  const [refunding, setRefunding] = useState<api.PaymentRecord | null>(null);
  const payments = useQuery({
    queryKey: ["merchant", merchantId, "payments", offset],
    queryFn: () => api.listMerchantPayments(merchantId, { limit: PAGE_SIZE, offset }),
  });

  return (
    <>
      <h2>Received payments</h2>
      <ErrorAlert error={payments.error} />
      {refunding && (
        <RefundForm
          payment={refunding}
          merchantId={merchantId}
          onDone={() => setRefunding(null)}
        />
      )}
      {payments.isPending ? (
        <Loading what="Loading payments" />
      ) : payments.data?.length === 0 && offset === 0 ? (
        <Empty>No payments received yet.</Empty>
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Reference</th>
                <th>Status</th>
                <th className="num">Amount</th>
                <th className="num">Refunded</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payments.data?.map((payment) => (
                <tr key={payment.id}>
                  <td data-label="When">
                    <DateTime value={payment.created_at} />
                  </td>
                  <td data-label="Reference">{payment.reference}</td>
                  <td data-label="Status">
                    <StatusBadge status={payment.status} />
                  </td>
                  <td className="num" data-label="Amount">
                    <Money minor={payment.amount_minor} currency={payment.currency} />
                  </td>
                  <td className="num" data-label="Refunded">
                    <Money minor={payment.refunded_amount_minor} currency={payment.currency} />
                  </td>
                  <td className="num" data-label="">
                    {REFUNDABLE.has(payment.status) && (
                      <button
                        type="button"
                        className="button button-small button-ghost"
                        onClick={() => setRefunding(payment)}
                      >
                        Refund
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
        Refund of <Money minor={refund.data.amount_minor} currency={payment.currency} /> for{" "}
        {payment.reference}: <StatusBadge status={refund.data.status} />{" "}
        {refund.data.failure_reason}{" "}
        <button type="button" className="button button-small button-ghost" onClick={onDone}>
          Close
        </button>
      </Notice>
    );
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      <h3>
        Refund {payment.reference} — up to <Money minor={remaining} currency={payment.currency} />
      </h3>
      <ErrorAlert error={refund.error} />
      <div className="row">
        <label>
          Amount ({payment.currency})
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
          Reason (optional)
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
          Cancel
        </button>
        <button type="submit" className="button" disabled={refund.isPending}>
          {refund.isPending ? "Refunding…" : "Refund"}
        </button>
      </div>
    </form>
  );
}

function WebhookEndpoints({ merchantId }: { merchantId: string }) {
  const queryClient = useQueryClient();
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
      <h2>Webhooks</h2>
      <p className="muted">
        FinCore POSTs payment events to these URLs, signed with HMAC-SHA256 using the endpoint&apos;s
        secret.
      </p>
      {revealed && (
        <div className="alert alert-warn" role="status">
          <strong>Signing secret for {revealed.url}</strong>
          <p>Save it now — it is shown only this once.</p>
          <code className="secret">{revealed.secret}</code> <CopyButton text={revealed.secret} />{" "}
          <button
            type="button"
            className="button button-small button-ghost"
            onClick={() => setRevealed(null)}
          >
            I saved it
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
          aria-label="Webhook URL"
          type="url"
          placeholder="https://example.com/fincore-webhooks"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          maxLength={2048}
        />
        <button type="submit" className="button" disabled={create.isPending}>
          Add endpoint
        </button>
      </form>
      {endpoints.isPending ? (
        <Loading what="Loading endpoints" />
      ) : mine.length === 0 ? (
        <Empty>No webhook endpoints for this merchant.</Empty>
      ) : (
        <ul className="list">
          {mine.map((endpoint) => (
            <li key={endpoint.id} className="card">
              <div className="list-row">
                <div>
                  <code>{endpoint.url}</code>
                  <div className="muted small">
                    {endpoint.consecutive_failures} consecutive failed deliveries · added{" "}
                    <DateTime value={endpoint.created_at} />
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
                      Enable
                    </button>
                  )}
                  <button
                    type="button"
                    className="button button-small button-ghost"
                    onClick={() => rotate.mutate(endpoint.id)}
                  >
                    Rotate secret
                  </button>
                  <button
                    type="button"
                    className="button button-small button-ghost"
                    onClick={() =>
                      setOpenEndpoint(openEndpoint === endpoint.id ? null : endpoint.id)
                    }
                  >
                    {openEndpoint === endpoint.id ? "Hide deliveries" : "Deliveries"}
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
  const [offset, setOffset] = useState(0);
  const deliveries = useQuery({
    queryKey: ["webhooks", endpointId, "deliveries", offset],
    queryFn: () => api.listWebhookDeliveries(endpointId, { limit: PAGE_SIZE, offset }),
  });
  if (deliveries.isPending) return <Loading what="Loading deliveries" />;
  if (deliveries.error) return <ErrorAlert error={deliveries.error} />;
  return (
    <>
      <DeliveriesTable deliveries={deliveries.data} />
      <Pager offset={offset} limit={PAGE_SIZE} count={deliveries.data.length} onChange={setOffset} />
    </>
  );
}

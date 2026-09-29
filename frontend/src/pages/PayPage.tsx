import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { OperationOutcome } from "../components/OperationOutcome";
import { ErrorAlert, Loading, Money } from "../components/ui";
import { validateAmount, walletLabel } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";

export function PayPage() {
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState("");
  const [merchantId, setMerchantId] = useState(params.get("merchant") ?? "");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  const source = wallets.data?.find((wallet) => wallet.id === sourceId) ?? wallets.data?.[0];

  const payment = useMutation({
    mutationFn: () =>
      api.createPayment(
        {
          source_wallet_id: source!.id,
          merchant_id: merchantId.trim(),
          amount: amount.trim(),
          currency: source!.currency,
          description: description.trim() || null,
        },
        idempotencyKey,
      ),
    onSuccess: () => {
      renewKey();
      void queryClient.invalidateQueries({ queryKey: ["wallets"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });

  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      if (payment.isError) renewKey();
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    const problem = validateAmount(amount, source.currency);
    setAmountError(problem);
    if (!problem) payment.mutate();
  }

  if (wallets.isPending) return <Loading what="Loading wallets" />;
  if (!wallets.data?.length) {
    return (
      <section className="page">
        <h1>Pay a merchant</h1>
        <p>
          You need a wallet first. <Link to="/">Create one</Link>.
        </p>
      </section>
    );
  }

  if (payment.isSuccess) {
    return (
      <section className="page narrow">
        <h1>Pay a merchant</h1>
        <OperationOutcome
          kind="Payment"
          status={payment.data.status}
          failureReason={payment.data.failure_reason}
          reference={payment.data.reference}
          amount={<Money minor={payment.data.amount_minor} currency={payment.data.currency} />}
        />
        <div className="actions">
          <Link to={`/transactions/${payment.data.id}`} className="button button-ghost">
            View details
          </Link>
          <button type="button" className="button" onClick={() => payment.reset()}>
            New payment
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="page narrow">
      <h1>Pay a merchant</h1>
      <form className="card form" onSubmit={onSubmit}>
        <ErrorAlert error={wallets.error ?? payment.error} />
        <label>
          From
          <select value={source?.id} onChange={(e) => edited(setSourceId)(e.target.value)}>
            {wallets.data.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Merchant id
          <input
            value={merchantId}
            onChange={(e) => edited(setMerchantId)(e.target.value)}
            required
            pattern="[0-9a-fA-F-]{36}"
            title="The merchant's id, e.g. 3f2b8c1e-…"
          />
        </label>
        <label>
          Amount ({source?.currency})
          <input
            value={amount}
            onChange={(e) => edited(setAmount)(e.target.value)}
            inputMode="decimal"
            placeholder="100.00"
            required
            aria-invalid={!!amountError}
          />
          {amountError && <span className="field-error">{amountError}</span>}
        </label>
        <label>
          Note (optional)
          <input
            value={description}
            onChange={(e) => edited(setDescription)(e.target.value)}
            maxLength={255}
          />
        </label>
        <button type="submit" className="button" disabled={payment.isPending}>
          {payment.isPending ? "Paying…" : "Pay"}
        </button>
      </form>
    </section>
  );
}

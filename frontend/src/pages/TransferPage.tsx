import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { ErrorAlert, Loading, Money } from "../components/ui";
import { OperationOutcome } from "../components/OperationOutcome";
import { validateAmount, walletLabel } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";

export function TransferPage() {
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState(params.get("from") ?? "");
  const [destinationId, setDestinationId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  const source = wallets.data?.find((wallet) => wallet.id === sourceId) ?? wallets.data?.[0];

  const transfer = useMutation({
    mutationFn: () =>
      api.createTransfer(
        {
          source_wallet_id: source!.id,
          destination_wallet_id: destinationId.trim(),
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

  // Editing the form turns it into a different request, which must not
  // reuse the previous attempt's Idempotency-Key.
  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      if (transfer.isError) renewKey();
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    const problem = validateAmount(amount, source.currency);
    setAmountError(problem);
    if (!problem) transfer.mutate();
  }

  if (wallets.isPending) return <Loading what="Loading wallets" />;
  if (!wallets.data?.length) {
    return (
      <section className="page">
        <h1>Send money</h1>
        <p>
          You need a wallet first. <Link to="/">Create one</Link>.
        </p>
      </section>
    );
  }

  if (transfer.isSuccess) {
    return (
      <section className="page narrow">
        <h1>Send money</h1>
        <OperationOutcome
          kind="Transfer"
          status={transfer.data.status}
          failureReason={transfer.data.failure_reason}
          reference={transfer.data.reference}
          amount={<Money minor={transfer.data.amount_minor} currency={transfer.data.currency} />}
        />
        <div className="actions">
          <Link to={`/transactions/${transfer.data.id}`} className="button button-ghost">
            View details
          </Link>
          <button type="button" className="button" onClick={() => transfer.reset()}>
            Send another
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="page narrow">
      <h1>Send money</h1>
      <form className="card form" onSubmit={onSubmit}>
        <ErrorAlert error={wallets.error ?? transfer.error} />
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
          To wallet id
          <input
            value={destinationId}
            onChange={(e) => edited(setDestinationId)(e.target.value)}
            placeholder="Recipient's wallet id"
            required
            pattern="[0-9a-fA-F-]{36}"
            title="A wallet id, e.g. 3f2b8c1e-…"
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
        <button type="submit" className="button" disabled={transfer.isPending}>
          {transfer.isPending ? "Sending…" : "Send"}
        </button>
      </form>
    </section>
  );
}

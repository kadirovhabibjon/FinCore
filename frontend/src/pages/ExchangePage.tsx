import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { ApiError } from "../api/client";
import { DateTime, ErrorAlert, Loading, Money, Notice } from "../components/ui";
import { formatMinor, validateAmount, walletLabel } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";

const QUOTE_DELAY_MS = 350;

/** "1 USD = 11,835.85 UZS", whichever way round reads as a number
 * above one. The server's rate is a decimal string; this is display
 * only, never used to compute an amount. */
function rateLine(quote: api.ExchangeQuote): string {
  const rate = Number(quote.rate);
  if (!Number.isFinite(rate) || rate <= 0) return "";
  const format = (value: number) =>
    new Intl.NumberFormat("en-US", { maximumFractionDigits: value >= 100 ? 2 : 4 }).format(value);
  return rate >= 1
    ? `1 ${quote.source_currency} = ${format(rate)} ${quote.destination_currency}`
    : `1 ${quote.destination_currency} = ${format(1 / rate)} ${quote.source_currency}`;
}

/** Exchanging money between the customer's own wallets. The amount
 * they will receive is shown before anything happens, and the exchange
 * is only made for exactly that amount. */
export function ExchangePage() {
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState("");
  const [destinationId, setDestinationId] = useState("");
  const [amount, setAmount] = useState("");
  // What the quote is asked for: the typed amount, once typing pauses.
  const [settled, setSettled] = useState("");
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  const source = wallets.data?.find((wallet) => wallet.id === sourceId) ?? wallets.data?.[0];
  const others = wallets.data?.filter((wallet) => wallet.currency !== source?.currency) ?? [];
  const destination = others.find((wallet) => wallet.id === destinationId) ?? others[0];
  const amountProblem =
    source && amount.trim() ? validateAmount(amount, source.currency) : null;
  const askable = !!source && !!destination && !!amount.trim() && !amountProblem;

  useEffect(() => {
    const timer = setTimeout(() => setSettled(amount.trim()), QUOTE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [amount]);

  const quote = useQuery({
    queryKey: ["exchange-quote", source?.id, destination?.id, settled],
    queryFn: () => api.getExchangeQuote(source!.id, destination!.id, settled),
    enabled: askable && settled === amount.trim(),
    retry: false,
    // A quote is only as good as the moment it was made.
    staleTime: 0,
    gcTime: 0,
  });
  const offer = askable && settled === amount.trim() ? quote.data : undefined;

  const exchange = useMutation({
    mutationFn: () =>
      api.createExchange(
        {
          source_wallet_id: source!.id,
          destination_wallet_id: destination!.id,
          amount: settled,
          expected_destination_amount_minor: offer!.destination_amount_minor,
        },
        idempotencyKey,
      ),
    onSuccess: () => {
      renewKey();
      void queryClient.invalidateQueries({ queryKey: ["wallets"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
    onError: (error) => {
      // The rate moved: show what the amount buys now.
      if (error instanceof ApiError && error.status === 409) void quote.refetch();
    },
  });

  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      // A changed form is a different exchange: a new key, and the last
      // attempt's outcome no longer describes it.
      if (!exchange.isIdle) {
        renewKey();
        exchange.reset();
      }
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (offer) exchange.mutate();
  }

  if (wallets.isPending) return <Loading what="Loading wallets" />;
  if (!source || others.length === 0) {
    return (
      <section className="page narrow">
        <h1>Exchange</h1>
        <ErrorAlert error={wallets.error} />
        <p>
          An exchange is between two of your own wallets in different currencies. You need a UZS
          wallet and a USD wallet. <Link to="/">Create the missing one</Link>.
        </p>
      </section>
    );
  }

  if (exchange.isSuccess) {
    const done = exchange.data;
    const failed = done.status === "FAILED";
    const finished = done.status === "COMPLETED";
    return (
      <section className="page narrow">
        <h1>Exchange</h1>
        {finished && (
          <Notice>
            Exchanged <Money minor={done.source_amount_minor} currency={done.source_currency} /> for{" "}
            <strong>
              <Money minor={done.destination_amount_minor} currency={done.destination_currency} />
            </strong>
            . Reference {done.reference}.
          </Notice>
        )}
        {failed && (
          <div className="alert alert-error" role="alert">
            The exchange didn&apos;t go through
            {done.failure_reason ? `: ${done.failure_reason}` : ""}. Your money is in your wallet.
          </div>
        )}
        {!finished && !failed && (
          <Notice>
            Your exchange {done.reference} is being completed. It will appear in History and your
            balances will update shortly; you don&apos;t need to do it again.
          </Notice>
        )}
        <div className="actions">
          <Link to="/transactions" className="button button-ghost">
            History
          </Link>
          <button
            type="button"
            className="button"
            onClick={() => {
              setAmount("");
              exchange.reset();
            }}
          >
            Exchange again
          </button>
        </div>
      </section>
    );
  }

  const rateChanged = exchange.error instanceof ApiError && exchange.error.status === 409;
  return (
    <section className="page narrow">
      <h1>Exchange</h1>
      <p className="muted">Between your own wallets, at the current rate. No fee.</p>
      <form className="card form" onSubmit={onSubmit}>
        <ErrorAlert error={wallets.error ?? (rateChanged ? null : exchange.error)} />
        {rateChanged && (
          <div className="alert alert-warn" role="alert">
            The rate changed while you were looking. Nothing was exchanged: check the new amount
            below and confirm again.
          </div>
        )}
        <label>
          From
          <select value={source.id} onChange={(e) => edited(setSourceId)(e.target.value)}>
            {wallets.data?.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>
        <label>
          To
          <select
            value={destination?.id}
            onChange={(e) => edited(setDestinationId)(e.target.value)}
          >
            {others.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Amount ({source.currency})
          <input
            value={amount}
            onChange={(e) => edited(setAmount)(e.target.value)}
            inputMode="decimal"
            placeholder="100.00"
            required
            aria-invalid={!!amountProblem}
          />
          {amountProblem && <span className="field-error">{amountProblem}</span>}
        </label>
        <div className="exchange-quote" aria-live="polite">
          {!askable ? (
            <span className="muted">Enter an amount to see what you&apos;ll get.</span>
          ) : quote.error ? (
            <ErrorAlert error={quote.error} />
          ) : offer ? (
            <>
              <span className="muted">You get</span>
              <strong className="exchange-amount">
                <Money minor={offer.destination_amount_minor} currency={offer.destination_currency} />
              </strong>
              <span className="muted small">
                {rateLine(offer)} · rate from <DateTime value={offer.rate_updated_at} />
              </span>
            </>
          ) : (
            <span className="muted">Getting the rate…</span>
          )}
        </div>
        <button type="submit" className="button" disabled={!offer || exchange.isPending}>
          {exchange.isPending
            ? "Exchanging…"
            : offer
              ? `Exchange for ${formatMinor(offer.destination_amount_minor, offer.destination_currency)}`
              : "Exchange"}
        </button>
      </form>
    </section>
  );
}

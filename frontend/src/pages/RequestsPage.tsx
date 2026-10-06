import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { ApiError } from "../api/client";
import {
  DateTime,
  Empty,
  ErrorAlert,
  Loading,
  Money,
  Notice,
  StatusBadge,
} from "../components/ui";
import { CARD_NUMBER_LENGTH, cardDigits, formatCardNumber, isValidCardNumber } from "../lib/card";
import { validateAmount, walletLabel } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";
import { useI18n, type MessageKey } from "../i18n";

/** Asking someone for money, and answering those who ask. A request
 * moves nothing by itself: paying one is an ordinary transfer. */
export function RequestsPage() {
  const { t, tr } = useI18n();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const requests = useQuery({
    queryKey: ["money-requests"],
    queryFn: api.listMoneyRequests,
    // Someone may ask, pay or decline while this page is open.
    refetchInterval: 20_000,
  });

  const incoming = requests.data?.filter((item) => item.direction === "INCOMING") ?? [];
  const outgoing = requests.data?.filter((item) => item.direction === "OUTGOING") ?? [];

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("requests.title")}</h1>
          <p className="muted">{t("requests.subtitle")}</p>
        </div>
      </header>
      <ErrorAlert error={requests.error ?? wallets.error} />

      <h2>{t("requests.incoming")}</h2>
      {requests.isPending || wallets.isPending ? (
        <Loading what={t("requests.loading")} />
      ) : incoming.length === 0 ? (
        <Empty>{t("requests.noIncoming")}</Empty>
      ) : (
        <ul className="list">
          {incoming.map((item) => (
            <IncomingRequest key={item.id} request={item} wallets={wallets.data ?? []} />
          ))}
        </ul>
      )}

      <h2>{t("requests.ask")}</h2>
      {wallets.data && wallets.data.length > 0 ? (
        <RequestForm wallets={wallets.data} />
      ) : (
        !wallets.isPending && (
          <p>
            {tr("requests.needWallet", { link: <Link to="/">{t("send.createOne")}</Link> })}
          </p>
        )
      )}

      <h2>{t("requests.outgoing")}</h2>
      {requests.isPending ? (
        <Loading what={t("requests.loading")} />
      ) : outgoing.length === 0 ? (
        <Empty>{t("requests.noOutgoing")}</Empty>
      ) : (
        <ul className="list">
          {outgoing.map((item) => (
            <OutgoingRequest key={item.id} request={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

function RequestSummary({
  request,
  template,
}: {
  request: api.MoneyRequest;
  template: MessageKey;
}) {
  const { t, tr } = useI18n();
  return (
    <div>
      {tr(template, {
        amount: (
          <strong>
            <Money minor={request.amount_minor} currency={request.currency} />
          </strong>
        ),
        name: request.counterparty_name ?? t("requests.someone"),
      })}
      {request.note && <div className="request-note">“{request.note}”</div>}
      <div className="muted small">
        {request.reference} · <DateTime value={request.created_at} />
      </div>
    </div>
  );
}

function IncomingRequest({
  request,
  wallets,
}: {
  request: api.MoneyRequest;
  wallets: api.Wallet[];
}) {
  const queryClient = useQueryClient();
  const { t, tr } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [idempotencyKey, renewKey] = useIdempotencyKey();
  // The wallet it would be paid from: the caller's wallet in that currency.
  const source = wallets.find((wallet) => wallet.currency === request.currency);

  function settled() {
    void queryClient.invalidateQueries({ queryKey: ["money-requests"] });
    void queryClient.invalidateQueries({ queryKey: ["wallets"] });
    void queryClient.invalidateQueries({ queryKey: ["transactions"] });
  }
  const pay = useMutation({
    mutationFn: () => api.payMoneyRequest(request.id, source!.id, idempotencyKey),
    onSuccess: () => {
      renewKey();
      setConfirming(false);
      settled();
    },
    // 409: someone (another device) answered it first. Show what it is now.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) settled();
    },
  });
  const decline = useMutation({
    mutationFn: () => api.declineMoneyRequest(request.id),
    onSettled: settled,
  });
  const open = request.status === "PENDING";
  const available = source ? source.balance_minor - source.held_minor : 0;

  return (
    <li className="card">
      <div className="list-row">
        <RequestSummary request={request} template="requests.askedBy" />
        <div className="actions">
          {!open && <StatusBadge status={request.status} />}
          {open && !confirming && (
            <>
              <button
                type="button"
                className="button button-small"
                disabled={!source}
                onClick={() => setConfirming(true)}
              >
                {t("requests.pay")}
              </button>
              <button
                type="button"
                className="button button-small button-ghost"
                disabled={decline.isPending}
                onClick={() => decline.mutate()}
              >
                {t("requests.decline")}
              </button>
            </>
          )}
        </div>
      </div>
      {open && !source && (
        <p className="field-error">{t("requests.noWallet", { currency: request.currency })}</p>
      )}
      {request.last_failure && open && (
        <p className="field-error">
          {t("requests.lastFailure", { reason: request.last_failure })}
        </p>
      )}
      {request.status === "PROCESSING" && (
        <p className="muted small">{t("requests.processing")}</p>
      )}
      <ErrorAlert error={pay.error ?? decline.error} />
      {open && confirming && source && (
        <div className="request-confirm">
          <p>
            {tr("requests.confirm", {
              amount: <Money minor={request.amount_minor} currency={request.currency} />,
              name: <strong>{request.counterparty_name ?? t("requests.requester")}</strong>,
              currency: request.currency,
              available: <Money minor={available} currency={request.currency} />,
            })}
          </p>
          <div className="actions">
            <button
              type="button"
              className="button button-small button-ghost"
              disabled={pay.isPending}
              onClick={() => setConfirming(false)}
            >
              {t("requests.notNow")}
            </button>
            <button
              type="button"
              className="button button-small"
              disabled={pay.isPending}
              onClick={() => pay.mutate()}
            >
              {pay.isPending ? t("send.sending") : t("requests.yesSend")}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function OutgoingRequest({ request }: { request: api.MoneyRequest }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const cancel = useMutation({
    mutationFn: () => api.cancelMoneyRequest(request.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["money-requests"] }),
  });
  return (
    <li className="card">
      <div className="list-row">
        <RequestSummary request={request} template="requests.askedFrom" />
        <div className="actions">
          <StatusBadge status={request.status} />
          {request.status === "PENDING" && (
            <button
              type="button"
              className="button button-small button-ghost"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              {t("requests.cancel")}
            </button>
          )}
        </div>
      </div>
      <ErrorAlert error={cancel.error} />
    </li>
  );
}

function RequestForm({ wallets }: { wallets: api.Wallet[] }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [walletId, setWalletId] = useState(wallets[0]?.id ?? "");
  const [cardNumber, setCardNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const wallet = wallets.find((item) => item.id === walletId) ?? wallets[0];

  // Who would be asked, shown before the request is sent.
  const cardValid = isValidCardNumber(cardNumber);
  const lookup = useQuery({
    queryKey: ["recipient", cardNumber],
    queryFn: () => api.findRecipient(cardNumber),
    enabled: cardValid,
    retry: false,
    staleTime: 60_000,
  });
  const person = cardValid ? lookup.data : undefined;
  let personProblem: string | null = null;
  if (cardNumber.length === CARD_NUMBER_LENGTH && !cardValid) {
    personProblem = t("requests.badDigit");
  } else if (cardValid && lookup.error instanceof ApiError && lookup.error.status === 404) {
    personProblem = t("requests.noCustomer");
  } else if (cardValid && lookup.error) {
    personProblem = t("send.lookupFailed");
  } else if (person?.own) {
    personProblem = t("requests.ownCard");
  } else if (person && wallet && person.currency !== wallet.currency) {
    personProblem = t("requests.otherCurrency", { currency: person.currency });
  }
  const canAsk = !!person && !personProblem;

  const ask = useMutation({
    mutationFn: api.createMoneyRequest,
    onSuccess: () => {
      setCardNumber("");
      setAmount("");
      setNote("");
      void queryClient.invalidateQueries({ queryKey: ["money-requests"] });
    },
  });

  function edited(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      if (!ask.isIdle) ask.reset();
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!wallet || !canAsk) return;
    const problem = validateAmount(amount, wallet.currency);
    setAmountError(problem);
    if (problem) return;
    ask.mutate({
      wallet_id: wallet.id,
      from_card_number: cardNumber,
      amount: amount.trim(),
      note: note.trim() || null,
    });
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      {ask.isSuccess && (
        <Notice>
          {t("requests.sent", { name: ask.data.counterparty_name ?? t("requests.them") })}
        </Notice>
      )}
      <ErrorAlert error={ask.error} />
      <label>
        {t("requests.receiveInto")}
        <select value={wallet?.id} onChange={(e) => edited(setWalletId)(e.target.value)}>
          {wallets.map((item) => (
            <option key={item.id} value={item.id}>
              {walletLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <div className="field">
        <label>
          {t("requests.askCard")}
          <input
            value={formatCardNumber(cardNumber)}
            onChange={(e) => edited(setCardNumber)(cardDigits(e.target.value))}
            placeholder="9955 0000 0000 0000"
            inputMode="numeric"
            autoComplete="off"
            required
            aria-invalid={!!personProblem}
          />
        </label>
        <span aria-live="polite">
          {personProblem ? (
            <span className="field-error">{personProblem}</span>
          ) : person ? (
            <span className="recipient">
              <span className="recipient-avatar" aria-hidden="true">
                {person.display_name.slice(0, 1).toUpperCase()}
              </span>
              <strong>{person.display_name}</strong>
            </span>
          ) : cardValid ? (
            <span className="muted small">{t("requests.lookingUp")}</span>
          ) : (
            <span className="muted small">{t("requests.cardHint")}</span>
          )}
        </span>
      </div>
      <div className="row">
        <label>
          {t("send.amount", { currency: wallet?.currency ?? "" })}
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
          {t("requests.whatFor")}
          <input value={note} onChange={(e) => edited(setNote)(e.target.value)} maxLength={255} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="button" disabled={ask.isPending || !canAsk}>
          {ask.isPending ? t("send.sending") : t("requests.send")}
        </button>
      </div>
    </form>
  );
}

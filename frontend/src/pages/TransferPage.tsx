import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { ApiError } from "../api/client";
import { ErrorAlert, Loading, Money } from "../components/ui";
import { OperationOutcome } from "../components/OperationOutcome";
import { QrScanner } from "../components/QrScanner";
import {
  CARD_NUMBER_LENGTH,
  cardDigits,
  formatCardNumber,
  isValidCardNumber,
} from "../lib/card";
import { validateAmount, walletLabel } from "../lib/money";
import { cardFromScan } from "../lib/qr";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";
import { useI18n } from "../i18n";

export function TransferPage() {
  const [params] = useSearchParams();
  const { t, tr } = useI18n();
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState(params.get("from") ?? "");
  // ?to= is what a FinCore QR code links to: the card arrives filled in.
  // Anything in it that is not a well-formed card is ignored.
  const [cardNumber, setCardNumber] = useState(() => cardFromScan(params.get("to") ?? "") ?? "");
  const [scanning, setScanning] = useState(false);
  const [scanProblem, setScanProblem] = useState(false);
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  const source =
    wallets.data?.find((wallet) => wallet.id === sourceId) ?? wallets.data?.[0];

  // People this customer has sent money to before, to pick instead of
  // typing a card number. Nice to have: a failure just hides the list.
  const recents = useQuery({
    queryKey: ["recipients"],
    queryFn: api.listRecentRecipients,
    retry: false,
  });
  // Only those the chosen wallet can actually send to.
  const recentHere = (recents.data ?? []).filter(
    (item) => item.currency === source?.currency,
  );

  // The recipient is looked up as soon as a complete, well-formed number
  // is typed, so the sender sees a name before anything is sent.
  const cardComplete = cardNumber.length === CARD_NUMBER_LENGTH;
  const cardValid = isValidCardNumber(cardNumber);
  const lookup = useQuery({
    queryKey: ["recipient", cardNumber],
    queryFn: () => api.findRecipient(cardNumber),
    enabled: cardValid,
    retry: false,
    staleTime: 60_000,
  });
  const recipient = cardValid ? lookup.data : undefined;
  const notFound =
    lookup.error instanceof ApiError && lookup.error.status === 404;
  let recipientProblem: string | null = null;
  if (cardComplete && !cardValid) {
    recipientProblem = t("send.badDigit");
  } else if (cardValid && notFound) {
    recipientProblem =
      t("send.noSuchCard");
  } else if (cardValid && lookup.error) {
    recipientProblem =
      t("send.lookupFailed");
  } else if (recipient && source && recipient.wallet_id === source.id) {
    recipientProblem = t("send.ownWallet");
  } else if (recipient && source && recipient.currency !== source.currency) {
    recipientProblem = t("send.otherCurrency", { currency: recipient.currency });
  }
  const canSend = !!recipient && !recipientProblem;

  const transfer = useMutation({
    mutationFn: () =>
      api.createTransfer(
        {
          source_wallet_id: source!.id,
          destination_wallet_id: recipient!.wallet_id,
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
      void queryClient.invalidateQueries({ queryKey: ["recipients"] });
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
    if (!source || !canSend) return;
    const problem = validateAmount(amount, source.currency);
    setAmountError(problem);
    if (!problem) transfer.mutate();
  }

  if (wallets.isPending) return <Loading what={t("wallets.loading")} />;
  if (!wallets.data?.length) {
    return (
      <section className="page">
        <h1>{t("send.title")}</h1>
        <p>
          {tr("send.needWallet", { link: <Link to="/">{t("send.createOne")}</Link> })}
        </p>
      </section>
    );
  }

  if (transfer.isSuccess) {
    return (
      <section className="page narrow">
        <h1>{t("send.title")}</h1>
        <OperationOutcome
          kind={t("kind.transfer")}
          status={transfer.data.status}
          failureReason={transfer.data.failure_reason}
          reference={transfer.data.reference}
          amount={
            <Money
              minor={transfer.data.amount_minor}
              currency={transfer.data.currency}
            />
          }
        />
        {recipient && (
          <p className="muted">
            {t("send.toLine", {
              name: recipient.display_name,
              card: formatCardNumber(cardNumber),
            })}
          </p>
        )}
        <div className="actions">
          <Link
            to={`/transactions/${transfer.data.id}`}
            className="button button-ghost"
          >
            {t("send.details")}
          </Link>
          <button
            type="button"
            className="button"
            onClick={() => {
              // A fresh form: the previous recipient and amount must not
              // be one accidental click away from being sent again.
              setCardNumber("");
              setAmount("");
              setDescription("");
              transfer.reset();
            }}
          >
            {t("send.another")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="page narrow">
      <h1>{t("send.title")}</h1>
      <form className="card form" onSubmit={onSubmit}>
        <ErrorAlert error={wallets.error ?? transfer.error} />
        <label>
          {t("send.from")}
          <select
            value={source?.id}
            onChange={(e) => edited(setSourceId)(e.target.value)}
          >
            {wallets.data.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>
        {recentHere.length > 0 && (
          <div className="field">
            <span className="field-label" id="recent-label">
              {t("send.recent")}
            </span>
            <div
              className="recipient-chips"
              role="group"
              aria-labelledby="recent-label"
            >
              {recentHere.map((item) => (
                <button
                  key={item.card_number}
                  type="button"
                  className="recipient-chip"
                  aria-pressed={item.card_number === cardNumber}
                  // Fills the card in; the lookup below still runs, so a
                  // card that stopped accepting money is caught as usual.
                  onClick={() => edited(setCardNumber)(item.card_number)}
                >
                  <span className="recipient-avatar" aria-hidden="true">
                    {(item.display_name ?? "•").slice(0, 1).toUpperCase()}
                  </span>
                  <span>
                    <strong>{item.display_name ?? t("send.card")}</strong>
                    <span className="muted small">
                      {" "}
                      ···· {item.card_number.slice(-4)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="field">
          {scanning && (
            <QrScanner
              onRead={(text) => {
                const card = cardFromScan(text);
                // Something else's QR code: keep looking, but say so.
                setScanProblem(card === null);
                if (card === null) return;
                edited(setCardNumber)(card);
                setScanning(false);
              }}
              onClose={() => {
                setScanning(false);
                setScanProblem(false);
              }}
            />
          )}
          {scanning && scanProblem && (
            <span className="field-error">{t("send.notFincoreQr")}</span>
          )}
          <label>
            {t("send.toCard")}
            <input
              value={formatCardNumber(cardNumber)}
              onChange={(e) =>
                edited(setCardNumber)(cardDigits(e.target.value))
              }
              placeholder="9955 0000 0000 0000"
              inputMode="numeric"
              autoComplete="off"
              required
              aria-invalid={!!recipientProblem}
              aria-describedby="recipient-status"
            />
          </label>
          {!scanning && (
            <button
              type="button"
              className="button button-small button-ghost scan-button"
              onClick={() => setScanning(true)}
            >
              {t("send.scan")}
            </button>
          )}
          <span id="recipient-status" aria-live="polite">
            {recipientProblem ? (
              <span className="field-error">{recipientProblem}</span>
            ) : recipient ? (
              <span className="recipient">
                <span className="recipient-avatar" aria-hidden="true">
                  {recipient.display_name.slice(0, 1).toUpperCase()}
                </span>
                <span>
                  <strong>{recipient.display_name}</strong>
                  {recipient.own && t("send.you")}
                  <span className="muted small">
                    {" "}
                    · {t("wallet.name", { currency: recipient.currency })}
                  </span>
                </span>
              </span>
            ) : cardValid ? (
              <span className="muted small">{t("send.lookingUp")}</span>
            ) : (
              <span className="muted small">
                {t("send.cardHint")}
              </span>
            )}
          </span>
        </div>
        <label>
          {t("send.amount", { currency: source?.currency ?? "" })}
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
          {t("send.note")}
          <input
            value={description}
            onChange={(e) => edited(setDescription)(e.target.value)}
            maxLength={255}
          />
        </label>
        <button
          type="submit"
          className="button"
          disabled={transfer.isPending || !canSend}
        >
          {transfer.isPending ? t("send.sending") : t("send.submit")}
        </button>
      </form>
    </section>
  );
}

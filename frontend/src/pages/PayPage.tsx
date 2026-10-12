import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { OperationOutcome } from "../components/OperationOutcome";
import { ErrorAlert, Loading, Money } from "../components/ui";
import { QrScanner } from "../components/QrScanner";
import { BlockedNotice } from "../components/WalletSettings";
import { merchantFromScan } from "../lib/qr";
import { useDailyLimit } from "../lib/useDailyLimit";
import { validateAmount, walletLabel } from "../lib/money";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";
import { useI18n } from "../i18n";

const MERCHANT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function PayPage() {
  const [params] = useSearchParams();
  const { t, tr } = useI18n();
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState("");
  // ?merchant= (and ?amount=) is what a merchant's QR code links to.
  const [merchantId, setMerchantId] = useState(params.get("merchant") ?? "");
  const [amount, setAmount] = useState(params.get("amount") ?? "");
  const [scanning, setScanning] = useState(false);
  const [scanProblem, setScanProblem] = useState(false);

  // Whose id it is, as soon as it is a whole one: the customer sees a
  // name before paying. A lookup that fails doesn't stop the payment -
  // the server decides that - it only can't show the name.
  const wellFormed = MERCHANT_ID.test(merchantId.trim());
  const lookup = useQuery({
    queryKey: ["merchant-to-pay", merchantId.trim().toLowerCase()],
    queryFn: () => api.findMerchant(merchantId.trim()),
    enabled: wellFormed,
    retry: false,
    staleTime: 60_000,
  });
  const found = wellFormed ? lookup.data : undefined;
  const unknown =
    wellFormed && lookup.error instanceof ApiError && lookup.error.status === 404;
  const cannotPay = unknown || found?.active === false;
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
      void queryClient.invalidateQueries({ queryKey: ["limit"] });
    },
  });
  const dailyLimit = useDailyLimit(source);

  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      if (payment.isError) renewKey();
    };
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    if (source.blocked || cannotPay) return;
    const problem = validateAmount(amount, source.currency) ?? dailyLimit.over(amount);
    setAmountError(problem);
    if (!problem) payment.mutate();
  }

  if (wallets.isPending) return <Loading what={t("wallets.loading")} />;
  if (!wallets.data?.length) {
    return (
      <section className="page">
        <h1>{t("pay.title")}</h1>
        <p>
          {tr("send.needWallet", { link: <Link to="/">{t("send.createOne")}</Link> })}
        </p>
      </section>
    );
  }

  if (payment.isSuccess) {
    return (
      <section className="page narrow">
        <h1>{t("pay.title")}</h1>
        <OperationOutcome
          kind={t("kind.payment")}
          status={payment.data.status}
          failureReason={payment.data.failure_reason}
          reference={payment.data.reference}
          amount={<Money minor={payment.data.amount_minor} currency={payment.data.currency} />}
        />
        <div className="actions">
          <Link to={`/transactions/${payment.data.id}`} className="button button-ghost">
            {t("send.details")}
          </Link>
          <button type="button" className="button" onClick={() => payment.reset()}>
            {t("pay.new")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="page narrow">
      <p>
        <Link to="/pay">{t("services.all")}</Link>
      </p>
      <h1>{t("pay.title")}</h1>
      <form className="card form" onSubmit={onSubmit}>
        <ErrorAlert error={wallets.error ?? payment.error} />
        <BlockedNotice wallet={source} />
        <label>
          {t("send.from")}
          <select value={source?.id} onChange={(e) => edited(setSourceId)(e.target.value)}>
            {wallets.data.map((wallet) => (
              <option key={wallet.id} value={wallet.id}>
                {walletLabel(wallet)}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          {scanning && (
            <QrScanner
              onRead={(text) => {
                const scanned = merchantFromScan(text);
                // Something else's QR code: keep looking, but say so.
                setScanProblem(scanned === null);
                if (scanned === null) return;
                edited(setMerchantId)(scanned.merchantId);
                if (scanned.amount) setAmount(scanned.amount);
                setScanning(false);
              }}
              onClose={() => {
                setScanning(false);
                setScanProblem(false);
              }}
            />
          )}
          {scanning && scanProblem && (
            <span className="field-error">{t("pay.notMerchantQr")}</span>
          )}
          <label>
            {t("pay.merchantId")}
            <input
              value={merchantId}
              onChange={(e) => edited(setMerchantId)(e.target.value)}
              required
              pattern="[0-9a-fA-F-]{36}"
              title={t("pay.merchantHint")}
              aria-invalid={cannotPay}
              aria-describedby="merchant-status"
            />
          </label>
          {!scanning && (
            <button
              type="button"
              className="button button-small button-ghost scan-button"
              onClick={() => setScanning(true)}
            >
              {t("pay.scan")}
            </button>
          )}
          <span id="merchant-status" aria-live="polite">
            {unknown ? (
              <span className="field-error">{t("pay.noSuchMerchant")}</span>
            ) : found && !found.active ? (
              <span className="field-error">{t("pay.merchantInactive")}</span>
            ) : found ? (
              <span className="recipient">
                <span className="recipient-avatar" aria-hidden="true">
                  {found.name.slice(0, 1).toUpperCase()}
                </span>
                <strong>{found.name}</strong>
              </span>
            ) : wellFormed && lookup.error ? (
              <span className="muted small">{t("pay.merchantLookupFailed")}</span>
            ) : wellFormed ? (
              <span className="muted small">{t("pay.lookingUp")}</span>
            ) : (
              <span className="muted small">{t("pay.idHint")}</span>
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
        <button type="submit" className="button" disabled={payment.isPending || !!source?.blocked || cannotPay}>
          {payment.isPending ? t("pay.paying") : t("pay.submit")}
        </button>
      </form>
    </section>
  );
}

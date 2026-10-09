import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { OperationOutcome } from "../components/OperationOutcome";
import { SaveTemplate } from "../components/SaveTemplate";
import { BlockedNotice } from "../components/WalletSettings";
import { ErrorAlert, Loading, Money, Notice } from "../components/ui";
import { useI18n, type I18n } from "../i18n";
import { formatMinor, minorToInput, toMinor, validateAmount, walletLabel } from "../lib/money";
import { CATEGORY_ORDER, isValidAccount } from "../lib/services";
import { useDailyLimit } from "../lib/useDailyLimit";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";

/** A provider's name: brands as they are, the utilities translated. */
function serviceName(service: api.Service, i18n: I18n): string {
  return i18n.maybe(`provider.${service.code}`) ?? service.name;
}

/** Paying for services: a catalogue of providers, then one form. Which
 * provider is chosen lives in the URL (?service=), so the browser's
 * back button returns to the catalogue. */
export function ServicesPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const [params, setParams] = useSearchParams();
  const services = useQuery({ queryKey: ["services"], queryFn: api.listServices });
  const chosenCode = params.get("service");

  // An old link to the merchant form, which this page used to be.
  const merchant = params.get("merchant");
  if (merchant) return <Navigate to={`/pay/merchant?merchant=${merchant}`} replace />;

  if (services.isPending) return <Loading what={t("services.loading")} />;
  const chosen = services.data?.find((service) => service.code === chosenCode);

  if (chosenCode) {
    return (
      <section className="page narrow">
        <p>
          <Link to="/pay">{t("services.all")}</Link>
        </p>
        {chosen ? (
          <ServiceForm key={chosen.code} service={chosen} />
        ) : (
          <Notice>{t("services.unknown")}</Notice>
        )}
      </section>
    );
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("services.title")}</h1>
          <p className="muted">{t("services.subtitle")}</p>
        </div>
        <Link to="/pay/merchant" className="button button-ghost">
          {t("services.merchant")}
        </Link>
      </header>
      <ErrorAlert error={services.error} />
      <p className="muted small">{t("services.demo")}</p>
      {CATEGORY_ORDER.map((category) => {
        const inCategory = (services.data ?? []).filter((item) => item.category === category);
        if (inCategory.length === 0) return null;
        return (
          <section key={category} aria-labelledby={`category-${category}`}>
            <h2 id={`category-${category}`}>{t(`category.${category}`)}</h2>
            <div className="service-grid">
              {inCategory.map((service) => (
                <button
                  key={service.code}
                  type="button"
                  className="card service-tile"
                  onClick={() => setParams({ service: service.code })}
                >
                  <span className="recipient-avatar" aria-hidden="true">
                    {serviceName(service, i18n).slice(0, 1).toUpperCase()}
                  </span>
                  <span>{serviceName(service, i18n)}</span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </section>
  );
}

function ServiceForm({ service }: { service: api.Service }) {
  const i18n = useI18n();
  const { t, tr } = i18n;
  const queryClient = useQueryClient();
  const name = serviceName(service, i18n);
  const { currency, account_kind: kind } = service;
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  const [sourceId, setSourceId] = useState("");
  // A template's link carries the account and, if saved, the amount.
  const [params] = useSearchParams();
  const [account, setAccount] = useState(params.get("account") ?? "");
  const [amount, setAmount] = useState(params.get("amount") ?? "");
  const [accountError, setAccountError] = useState<string | null>(null);
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  // Providers are paid in one currency: only those cards can pay.
  const usable = (wallets.data ?? []).filter((wallet) => wallet.currency === currency);
  const source = usable.find((wallet) => wallet.id === sourceId) ?? usable[0];
  const dailyLimit = useDailyLimit(source);
  const range = {
    min: formatMinor(service.min_amount_minor, currency),
    max: formatMinor(service.max_amount_minor, currency),
  };

  const payment = useMutation({
    mutationFn: () =>
      api.payService(
        service.code,
        { source_wallet_id: source!.id, account: account.trim(), amount: amount.trim() },
        idempotencyKey,
      ),
    onSuccess: () => {
      renewKey();
      void queryClient.invalidateQueries({ queryKey: ["wallets"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["limit"] });
    },
  });

  // Editing the form turns it into a different request, which must not
  // reuse the previous attempt's Idempotency-Key.
  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      if (payment.isError) renewKey();
    };
  }

  function amountProblem(): string | null {
    const invalid = validateAmount(amount, currency);
    if (invalid) return invalid;
    const minor = toMinor(amount, currency);
    if (minor < service.min_amount_minor || minor > service.max_amount_minor) {
      return t("services.outOfRange", range);
    }
    return dailyLimit.over(amount);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source || source.blocked) return;
    const badAccount = isValidAccount(kind, account) ? null : t(`account.${kind}.bad`);
    const badAmount = amountProblem();
    setAccountError(badAccount);
    setAmountError(badAmount);
    if (!badAccount && !badAmount) payment.mutate();
  }

  if (wallets.isPending) return <Loading what={t("wallets.loading")} />;

  if (payment.isSuccess) {
    return (
      <>
        <h1>{name}</h1>
        <OperationOutcome
          kind={t("kind.servicePayment")}
          status={payment.data.status}
          failureReason={payment.data.failure_reason}
          reference={payment.data.reference}
          amount={<Money minor={payment.data.amount_minor} currency={payment.data.currency} />}
        />
        <p className="muted">
          {t("services.paidFor", {
            service: name,
            account: payment.data.service_account ?? account.trim(),
          })}
        </p>
        <div className="actions">
          <Link to={`/transactions/${payment.data.id}`} className="button button-ghost">
            {t("send.details")}
          </Link>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              // The account stays: the same bill is often paid again.
              // The amount doesn't, so a second tap can't repeat it.
              setAmount("");
              payment.reset();
            }}
          >
            {t("services.again", { service: name })}
          </button>
          <Link to="/pay" className="button">
            {t("services.another")}
          </Link>
        </div>
        {payment.data.status !== "FAILED" && payment.data.service_account && (
          <SaveTemplate
            suggestedName={name}
            what={{
              kind: "SERVICE",
              service_code: service.code,
              account: payment.data.service_account,
            }}
            amount={minorToInput(payment.data.amount_minor, payment.data.currency)}
            amountText={formatMinor(payment.data.amount_minor, payment.data.currency)}
          />
        )}
      </>
    );
  }

  return (
    <>
      <h1>{name}</h1>
      {usable.length === 0 ? (
        <Notice>
          {tr("services.needWallet", {
            currency,
            link: <Link to="/">{t("send.createOne")}</Link>,
          })}
        </Notice>
      ) : (
        <form className="card form" onSubmit={onSubmit} noValidate>
          <ErrorAlert error={wallets.error ?? payment.error} />
          <BlockedNotice wallet={source} />
          <label>
            {t("send.from")}
            <select value={source?.id} onChange={(e) => edited(setSourceId)(e.target.value)}>
              {usable.map((wallet) => (
                <option key={wallet.id} value={wallet.id}>
                  {walletLabel(wallet)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t(`account.${kind}`)}
            <input
              value={account}
              onChange={(e) => edited(setAccount)(e.target.value)}
              type={kind === "PHONE" ? "tel" : "text"}
              inputMode={kind === "PHONE" ? "tel" : kind === "ACCOUNT_NUMBER" ? "numeric" : "text"}
              placeholder={kind === "PHONE" ? "+998 90 123 45 67" : undefined}
              autoComplete="off"
              maxLength={64}
              aria-invalid={!!accountError}
            />
            {accountError ? (
              <span className="field-error">{accountError}</span>
            ) : (
              <span className="muted small">{t(`account.${kind}.hint`)}</span>
            )}
          </label>
          <label>
            {t("send.amount", { currency })}
            <input
              value={amount}
              onChange={(e) => edited(setAmount)(e.target.value)}
              inputMode="decimal"
              placeholder="50000"
              aria-invalid={!!amountError}
            />
            {amountError ? (
              <span className="field-error">{amountError}</span>
            ) : (
              <span className="muted small">{t("services.range", range)}</span>
            )}
          </label>
          <button
            type="submit"
            className="button"
            disabled={payment.isPending || !!source?.blocked}
          >
            {payment.isPending ? t("pay.paying") : t("pay.submit")}
          </button>
        </form>
      )}
    </>
  );
}

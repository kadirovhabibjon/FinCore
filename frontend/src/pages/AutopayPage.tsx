import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { ConfirmButton } from "../components/ConfirmButton";
import { DateTime, Empty, ErrorAlert, Loading, Notice, StatusBadge } from "../components/ui";
import { useI18n, type I18n } from "../i18n";
import { minorToInput, validateAmount, walletLabel } from "../lib/money";
import { reasonText } from "../lib/reasons";
import { templateSummary } from "../lib/templates";

/** "Monday" in the reader's language, for ISO weekday 1 to 7. */
function weekdayName(day: number, locale: string): string {
  // 2024-01-01 was a Monday.
  const date = new Date(Date.UTC(2024, 0, day));
  return new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(date);
}

function scheduleText(item: api.ScheduledPayment, { t, locale }: I18n): string {
  return item.interval === "WEEKLY"
    ? t("auto.everyWeek", { weekday: weekdayName(item.day, locale) })
    : t("auto.everyMonth", { day: item.day });
}

/** Payments made for the customer on a schedule: what there is, how
 * the last run of each went, and a form to add one from a template. */
export function AutopayPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const queryClient = useQueryClient();
  const scheduled = useQuery({
    queryKey: ["scheduled-payments"],
    queryFn: api.listScheduledPayments,
  });
  const services = useQuery({
    queryKey: ["services"],
    queryFn: api.listServices,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["scheduled-payments"] });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: api.ScheduledPayment["status"] }) =>
      api.setScheduledPaymentStatus(id, status),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: api.deleteScheduledPayment, onSuccess: refresh });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("auto.title")}</h1>
          <p className="muted">{t("auto.subtitle")}</p>
        </div>
        <Link to="/templates" className="button button-ghost">
          {t("tpl.title")}
        </Link>
      </header>
      <ErrorAlert error={scheduled.error ?? setStatus.error ?? remove.error} />
      {scheduled.isPending ? (
        <Loading what={t("auto.loading")} />
      ) : scheduled.data?.length === 0 ? (
        <Empty>{t("auto.empty")}</Empty>
      ) : (
        <ul className="list">
          {scheduled.data?.map((item) => {
            const paused = item.status === "PAUSED";
            return (
              <li key={item.id} className="card">
                <div className="list-row">
                  <div>
                    <strong>{item.name}</strong>
                    <div className="muted small">
                      {/* The same line a template shows: what, and how much. */}
                      {templateSummary({ ...item, id: item.id }, services.data ?? [], i18n)}
                    </div>
                    <div className="small">
                      {scheduleText(item, i18n)}
                      {" · "}
                      {paused ? (
                        <span className="muted">{t("auto.paused")}</span>
                      ) : (
                        t("auto.next", {
                          when: new Intl.DateTimeFormat(i18n.locale, {
                            dateStyle: "medium",
                          }).format(new Date(item.next_run_at)),
                        })
                      )}
                    </div>
                    <div className="muted small">
                      {item.last_status ? (
                        <>
                          <DateTime value={item.last_run_at ?? item.created_at} />{" "}
                          <StatusBadge status={item.last_status} />
                          {item.last_error && ` ${reasonText(item.last_error, i18n)}`}
                          {item.last_operation_id && (
                            <>
                              {" · "}
                              <Link to={`/transactions/${item.last_operation_id}`}>
                                {t("auto.receipt")}
                              </Link>
                            </>
                          )}
                        </>
                      ) : (
                        t("auto.lastNever")
                      )}
                    </div>
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      className="button button-small button-ghost"
                      disabled={setStatus.isPending}
                      onClick={() =>
                        setStatus.mutate({ id: item.id, status: paused ? "ACTIVE" : "PAUSED" })
                      }
                    >
                      {paused ? t("auto.resume") : t("auto.pause")}
                    </button>
                    <ConfirmButton
                      confirm={t("auto.confirmDelete")}
                      className="button button-small button-ghost"
                      disabled={remove.isPending}
                      onConfirm={() => remove.mutate(item.id)}
                    >
                      {t("auto.delete")}
                    </ConfirmButton>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <h2>{t("auto.new")}</h2>
      <NewSchedule services={services.data ?? []} onCreated={refresh} />
    </section>
  );
}

function NewSchedule({
  services,
  onCreated,
}: {
  services: api.Service[];
  onCreated: () => Promise<unknown>;
}) {
  const i18n = useI18n();
  const { t, locale } = i18n;
  const [params] = useSearchParams();
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.listTemplates });
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });
  // ?template= comes from the Templates page's "Schedule" link.
  const [templateId, setTemplateId] = useState(params.get("template") ?? "");
  const [walletId, setWalletId] = useState("");
  const [amount, setAmount] = useState<string | null>(null);
  const [amountError, setAmountError] = useState<string | null>(null);
  const [interval, setInterval] = useState<api.ScheduledPayment["interval"]>("MONTHLY");
  const [day, setDay] = useState(1);

  const template = templates.data?.find((item) => item.id === templateId) ?? templates.data?.[0];
  const usable = (wallets.data ?? []).filter((wallet) => wallet.currency === template?.currency);
  const wallet = usable.find((item) => item.id === walletId) ?? usable[0];
  // Until typed over, the amount is the template's own.
  const shownAmount =
    amount ??
    (template?.amount_minor != null ? minorToInput(template.amount_minor, template.currency) : "");

  const create = useMutation({
    mutationFn: () =>
      api.schedulePayment({
        name: template!.name,
        kind: template!.kind,
        service_code: template!.service_code,
        account: template!.service_account,
        card_number: template!.card_number,
        source_wallet_id: wallet!.id,
        amount: shownAmount.trim(),
        interval,
        day,
      }),
    onSuccess: () => {
      setAmount(null);
      return onCreated();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!template || !wallet) return;
    const problem = validateAmount(shownAmount, template.currency);
    setAmountError(problem);
    if (!problem) create.mutate();
  }

  if (templates.isPending || wallets.isPending) return <Loading what={t("tpl.loading")} />;
  if (!template) return <Notice>{t("auto.needTemplate")}</Notice>;

  const days = interval === "WEEKLY" ? 7 : 28;
  return (
    <form className="card form" onSubmit={onSubmit} noValidate>
      <ErrorAlert error={templates.error ?? wallets.error ?? create.error} />
      <label>
        {t("auto.template")}
        <select
          value={template.id}
          onChange={(event) => {
            setTemplateId(event.target.value);
            setAmount(null);
            create.reset();
          }}
        >
          {templates.data?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} — {templateSummary(item, services, i18n)}
            </option>
          ))}
        </select>
      </label>
      {wallet ? (
        <label>
          {t("auto.from")}
          <select value={wallet.id} onChange={(event) => setWalletId(event.target.value)}>
            {usable.map((item) => (
              <option key={item.id} value={item.id}>
                {walletLabel(item)}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <Notice>{t("auto.noWallet", { currency: template.currency })}</Notice>
      )}
      <label>
        {t("auto.amount", { currency: template.currency })}
        <input
          value={shownAmount}
          onChange={(event) => setAmount(event.target.value)}
          inputMode="decimal"
          aria-invalid={!!amountError}
        />
        {amountError && <span className="field-error">{amountError}</span>}
      </label>
      <div className="row">
        <label>
          {t("auto.how")}
          <select
            value={interval}
            onChange={(event) => {
              setInterval(event.target.value as api.ScheduledPayment["interval"]);
              setDay(1);
            }}
          >
            <option value="MONTHLY">{t("auto.monthly")}</option>
            <option value="WEEKLY">{t("auto.weekly")}</option>
          </select>
        </label>
        <label>
          {interval === "WEEKLY" ? t("auto.weekday") : t("auto.monthday")}
          <select value={day} onChange={(event) => setDay(Number(event.target.value))}>
            {Array.from({ length: days }, (_, index) => index + 1).map((value) => (
              <option key={value} value={value}>
                {interval === "WEEKLY" ? weekdayName(value, locale) : value}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="submit" className="button" disabled={create.isPending || !wallet}>
        {create.isPending ? t("auto.creating") : t("auto.create")}
      </button>
    </form>
  );
}

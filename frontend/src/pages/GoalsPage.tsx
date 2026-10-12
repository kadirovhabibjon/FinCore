import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { ConfirmButton } from "../components/ConfirmButton";
import { DateTime, Empty, ErrorAlert, Loading, Notice, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import {
  SUPPORTED_CURRENCIES,
  formatMinor,
  toMinor,
  validateAmount,
  walletLabel,
} from "../lib/money";
import { reasonText } from "../lib/reasons";
import { useIdempotencyKey } from "../lib/useIdempotencyKey";

/** Savings goals: what the customer is saving for, how far along each
 * is, and moving money in and out. The money is real - it leaves the
 * card - so every movement says plainly how it ended. */
export function GoalsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const goals = useQuery({ queryKey: ["goals"], queryFn: api.listGoals });
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: api.listWallets });

  const [name, setName] = useState("");
  const [currency, setCurrency] = useState(SUPPORTED_CURRENCIES[0] ?? "UZS");
  const [target, setTarget] = useState("");
  const [targetError, setTargetError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.createGoal({ name: name.trim(), currency, target: target.trim() }),
    onSuccess: () => {
      setName("");
      setTarget("");
      return queryClient.invalidateQueries({ queryKey: ["goals"] });
    },
  });

  function onCreate(event: FormEvent) {
    event.preventDefault();
    const problem = validateAmount(target, currency);
    setTargetError(problem);
    if (!problem && name.trim()) create.mutate();
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("goal.title")}</h1>
          <p className="muted">{t("goal.subtitle")}</p>
        </div>
      </header>
      <ErrorAlert error={goals.error ?? wallets.error} />
      {goals.isPending ? (
        <Loading what={t("goal.loading")} />
      ) : goals.data?.length === 0 ? (
        <Empty>{t("goal.empty")}</Empty>
      ) : (
        <ul className="list">
          {goals.data?.map((goal) => (
            <li key={goal.id} className="card">
              <Goal goal={goal} wallets={wallets.data ?? []} />
            </li>
          ))}
        </ul>
      )}

      <h2>{t("goal.new")}</h2>
      <form className="card form" onSubmit={onCreate} noValidate>
        <ErrorAlert error={create.error} />
        <label>
          {t("goal.name")}
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={60}
            placeholder={t("goal.namePlaceholder")}
            required
          />
        </label>
        <div className="row">
          <label>
            {t("goal.currency")}
            <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
              {SUPPORTED_CURRENCIES.map((code) => (
                <option key={code}>{code}</option>
              ))}
            </select>
          </label>
          <label>
            {t("goal.target", { currency })}
            <input
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              inputMode="decimal"
              aria-invalid={!!targetError}
            />
            {targetError && <span className="field-error">{targetError}</span>}
          </label>
        </div>
        <button type="submit" className="button" disabled={create.isPending || !name.trim()}>
          {create.isPending ? t("goal.creating") : t("goal.create")}
        </button>
      </form>
    </section>
  );
}

function Goal({ goal, wallets }: { goal: api.SavingsGoal; wallets: api.Wallet[] }) {
  const i18n = useI18n();
  const { t } = i18n;
  const queryClient = useQueryClient();
  const { currency } = goal;
  const [moving, setMoving] = useState<api.SavingsMovement["direction"] | null>(null);
  const [walletId, setWalletId] = useState("");
  const [amount, setAmount] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [idempotencyKey, renewKey] = useIdempotencyKey();

  const usable = wallets.filter((wallet) => wallet.currency === currency);
  const wallet = usable.find((item) => item.id === walletId) ?? usable[0];
  const movements = useQuery({
    queryKey: ["goals", goal.id, "movements"],
    queryFn: () => api.listGoalMovements(goal.id),
    retry: false,
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["wallets"] });
    return queryClient.invalidateQueries({ queryKey: ["goals"] });
  };
  const move = useMutation({
    mutationFn: () =>
      api.moveSavings(
        goal.id,
        moving!,
        { wallet_id: wallet!.id, amount: amount.trim() },
        idempotencyKey,
      ),
    onSuccess: () => {
      renewKey();
      setAmount("");
      setMoving(null);
      return refresh();
    },
  });
  const close = useMutation({ mutationFn: () => api.closeGoal(goal.id), onSuccess: refresh });

  function open(direction: api.SavingsMovement["direction"]) {
    setMoving(direction);
    setAmount("");
    setAmountError(null);
    move.reset();
  }

  function onMove(event: FormEvent) {
    event.preventDefault();
    if (!wallet || !moving) return;
    let problem = validateAmount(amount, currency);
    // The server decides for real; this saves a failed movement.
    if (!problem && moving === "WITHDRAW" && toMinor(amount, currency) > goal.saved_minor) {
      problem = t("goal.overSaved", { amount: formatMinor(goal.saved_minor, currency) });
    }
    setAmountError(problem);
    if (!problem) move.mutate();
  }

  const saved = formatMinor(goal.saved_minor, currency);
  const targetText = formatMinor(goal.target_minor, currency);
  const percent = Math.min(Math.floor((goal.saved_minor / goal.target_minor) * 100), 100);
  const left = goal.target_minor - goal.saved_minor;
  const last = move.data;

  return (
    <div className="goal">
      <div className="list-row">
        <div>
          <strong>{goal.name}</strong>
          <div className="muted small">
            {t("goal.progress", { saved, target: targetText })} ·{" "}
            {left > 0 ? t("goal.left", { amount: formatMinor(left, currency) }) : t("goal.reached")}
          </div>
        </div>
        <strong className="goal-percent" aria-hidden="true">
          {percent}%
        </strong>
      </div>
      <div
        className="goal-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={t("goal.progressLabel", {
          name: goal.name,
          saved,
          target: targetText,
          percent,
        })}
      >
        {/* Sized from the data, so it has to be a computed style. */}
        <span className="goal-bar" style={{ width: `${percent}%` }} />
      </div>

      {last && !moving && (
        <Notice>
          {last.status === "COMPLETED"
            ? t(`goal.done.${last.direction}`, {
                amount: formatMinor(last.amount_minor, currency),
              })
            : last.status === "PENDING"
              ? t("goal.pending", { amount: formatMinor(last.amount_minor, currency) })
              : t("goal.failed", { reason: reasonText(last.failure_reason ?? "", i18n) })}
        </Notice>
      )}
      <ErrorAlert error={close.error} />

      {moving ? (
        <form className="goal-move" onSubmit={onMove} noValidate>
          <ErrorAlert error={move.error} />
          {wallet ? (
            <label>
              {moving === "DEPOSIT" ? t("goal.from") : t("goal.to")}
              <select value={wallet.id} onChange={(event) => setWalletId(event.target.value)}>
                {usable.map((item) => (
                  <option key={item.id} value={item.id}>
                    {walletLabel(item)}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <Notice>{t("goal.noWallet", { currency })}</Notice>
          )}
          <label>
            {t("goal.amount", { currency })}
            <input
              value={amount}
              onChange={(event) => {
                setAmount(event.target.value);
                // An edited form is a different request.
                if (move.isError) renewKey();
              }}
              inputMode="decimal"
              aria-invalid={!!amountError}
              autoFocus
            />
            {amountError && <span className="field-error">{amountError}</span>}
          </label>
          <div className="actions">
            <button type="button" className="button button-ghost" onClick={() => setMoving(null)}>
              {t("goal.cancel")}
            </button>
            <button type="submit" className="button" disabled={move.isPending || !wallet}>
              {move.isPending
                ? t("goal.moving")
                : moving === "DEPOSIT"
                  ? t("goal.add")
                  : t("goal.take")}
            </button>
          </div>
        </form>
      ) : (
        <div className="actions">
          <button type="button" className="button button-small" onClick={() => open("DEPOSIT")}>
            {t("goal.addMoney")}
          </button>
          {goal.saved_minor > 0 ? (
            <button
              type="button"
              className="button button-small button-ghost"
              onClick={() => open("WITHDRAW")}
            >
              {t("goal.takeOut")}
            </button>
          ) : (
            <ConfirmButton
              confirm={t("goal.confirmClose")}
              className="button button-small button-ghost"
              disabled={close.isPending}
              onConfirm={() => close.mutate()}
            >
              {t("goal.close")}
            </ConfirmButton>
          )}
        </div>
      )}

      {(movements.data?.length ?? 0) > 0 && (
        <details className="goal-history">
          <summary>{t("goal.history")}</summary>
          <ul>
            {movements.data?.map((item) => (
              <li key={item.id}>
                <span>
                  {item.direction === "DEPOSIT" ? t("goal.in") : t("goal.out")}{" "}
                  <span className="muted small">
                    <DateTime value={item.created_at} />
                  </span>
                </span>
                <span>
                  {item.status !== "COMPLETED" && <StatusBadge status={item.status} />}{" "}
                  {item.direction === "DEPOSIT" ? "+" : "−"}
                  {formatMinor(item.amount_minor, currency)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

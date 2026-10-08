import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { formatMinor, validateAmount } from "../lib/money";
import { ErrorAlert, Loading, Notice } from "./ui";

/** What the owner can set on one of their cards: its name, whether it
 * is their main card, a block on money leaving it, and a daily limit. */
export function WalletSettings({ wallet }: { wallet: api.Wallet }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  // Every one of these changes what the wallet lists and pages show.
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["wallets"] });
    return queryClient.invalidateQueries({ queryKey: ["wallet", wallet.id] });
  };

  const [name, setName] = useState(wallet.name ?? "");
  const rename = useMutation({
    mutationFn: () => api.renameWallet(wallet.id, name.trim() || null),
    onSuccess: (saved) => {
      setName(saved.name ?? "");
      return refresh();
    },
  });
  const makeMain = useMutation({
    mutationFn: () => api.makeWalletPrimary(wallet.id),
    onSuccess: refresh,
  });
  const block = useMutation({
    mutationFn: () => api.setWalletBlocked(wallet.id, !wallet.blocked),
    onSuccess: refresh,
  });

  return (
    <section aria-labelledby="card-settings">
      <h2 id="card-settings">{t("card.settings")}</h2>
      <div className="card card-settings">
        <form
          className="card-setting"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            rename.mutate();
          }}
        >
          <ErrorAlert error={rename.error} />
          <label>
            {t("card.name")}
            <input
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                rename.reset();
              }}
              maxLength={40}
              placeholder={t("card.namePlaceholder")}
            />
          </label>
          <p className="muted small">{t("card.nameHint")}</p>
          <div className="actions">
            <button
              type="submit"
              className="button button-ghost"
              disabled={rename.isPending || name.trim() === (wallet.name ?? "")}
            >
              {rename.isPending ? t("card.saving") : t("card.save")}
            </button>
            {rename.isSuccess && <span className="muted small">{t("card.saved")}</span>}
          </div>
        </form>

        <div className="card-setting">
          <h3>{t("card.mainTitle")}</h3>
          <ErrorAlert error={makeMain.error} />
          <p className="muted">{wallet.is_primary ? t("card.isMain") : t("card.notMain")}</p>
          {!wallet.is_primary && (
            <div className="actions">
              <button
                type="button"
                className="button button-ghost"
                disabled={makeMain.isPending}
                onClick={() => makeMain.mutate()}
              >
                {t("card.makeMain")}
              </button>
            </div>
          )}
        </div>

        <div className="card-setting">
          <h3>{t("card.blockTitle")}</h3>
          <ErrorAlert error={block.error} />
          <p className="muted">{wallet.blocked ? t("card.blockedNow") : t("card.blockIntro")}</p>
          <div className="actions">
            <button
              type="button"
              className={wallet.blocked ? "button" : "button button-ghost button-danger"}
              disabled={block.isPending}
              onClick={() => block.mutate()}
            >
              {wallet.blocked ? t("card.unblock") : t("card.block")}
            </button>
          </div>
        </div>

        <DailyLimit wallet={wallet} />
      </div>
    </section>
  );
}

function DailyLimit({ wallet }: { wallet: api.Wallet }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { currency } = wallet;
  const limit = useQuery({
    queryKey: ["limit", wallet.id],
    queryFn: () => api.getWalletLimit(wallet.id),
  });
  const [amount, setAmount] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (dailyLimit: string | null) => api.setWalletLimit(wallet.id, dailyLimit),
    onSuccess: (saved) => {
      setAmount("");
      queryClient.setQueryData(["limit", wallet.id], saved);
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateAmount(amount, currency);
    setAmountError(problem);
    if (!problem) save.mutate(amount.trim());
  }

  const status = limit.data;
  return (
    <form className="card-setting" onSubmit={onSubmit}>
      <h3>{t("limit.title")}</h3>
      <ErrorAlert error={limit.error ?? save.error} />
      <p className="muted">{t("limit.intro")}</p>
      {limit.isPending ? (
        <Loading what={t("limit.loading")} />
      ) : status ? (
        <p aria-live="polite">
          {status.daily_limit_minor === null || status.remaining_minor === null
            ? `${t("limit.none")} ${t("limit.spentOnly", { spent: formatMinor(status.spent_minor, currency) })}`
            : t("limit.status", {
                limit: formatMinor(status.daily_limit_minor, currency),
                spent: formatMinor(status.spent_minor, currency),
                remaining: formatMinor(status.remaining_minor, currency),
              })}
        </p>
      ) : null}
      <label>
        {t("limit.amount", { currency })}
        <input
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          inputMode="decimal"
          placeholder="1000000.00"
          aria-invalid={!!amountError}
        />
        {amountError && <span className="field-error">{amountError}</span>}
      </label>
      <div className="actions">
        <button type="submit" className="button button-ghost" disabled={save.isPending || !amount}>
          {t("limit.set")}
        </button>
        {status?.daily_limit_minor != null && (
          <button
            type="button"
            className="button button-ghost"
            disabled={save.isPending}
            onClick={() => save.mutate(null)}
          >
            {t("limit.remove")}
          </button>
        )}
      </div>
    </form>
  );
}

/** Above a money form whose chosen card is blocked: says why nothing
 * can be sent and where to undo it. */
export function BlockedNotice({ wallet }: { wallet?: api.Wallet }) {
  const { t } = useI18n();
  if (!wallet?.blocked) return null;
  return (
    <Notice>
      {t("card.blockedSource")} <Link to={`/wallets/${wallet.id}`}>{t("card.openCard")}</Link>
    </Notice>
  );
}

import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { useI18n } from "../i18n";
import { PasswordInput } from "./PasswordInput";
import { ErrorAlert, Notice } from "./ui";

/** Two-step sign-in on the Account page. Turning it on: the password,
 * then the code emailed to the account - nothing changes until that
 * code is given, so a mailbox that doesn't work locks nobody out.
 * Turning it off: the password. */
export function TwoFactorSettings({ user }: { user: api.CurrentUser }) {
  const { t } = useI18n();
  const { refreshUser } = useAuth();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<api.TwoFactorChallenge | null>(null);
  const [done, setDone] = useState<"on" | "off" | null>(null);

  const finished = (state: "on" | "off") => {
    setPassword("");
    setCode("");
    setChallenge(null);
    setDone(state);
    return refreshUser();
  };
  const begin = useMutation({
    mutationFn: () => api.beginTwoFactor(password),
    onSuccess: (sent) => {
      setPassword("");
      setChallenge(sent);
    },
  });
  const confirm = useMutation({
    mutationFn: () => api.confirmTwoFactor(challenge!.challenge_id, code.trim()),
    onSuccess: () => finished("on"),
  });
  const disable = useMutation({
    mutationFn: () => api.disableTwoFactor(password),
    onSuccess: () => finished("off"),
  });
  const enabled = user.two_factor_enabled ?? false;

  if (challenge) {
    return (
      <form
        key="confirm"
        className="card form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          confirm.mutate();
        }}
      >
        <Notice>{t("twofa.confirmSent", { email: challenge.email_hint })}</Notice>
        <ErrorAlert error={confirm.error} />
        <label>
          {t("twofa.code")}
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="000000"
            required
            autoFocus
          />
        </label>
        <div className="actions">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              setChallenge(null);
              setCode("");
              confirm.reset();
            }}
          >
            {t("twofa.cancel")}
          </button>
          <button type="submit" className="button" disabled={confirm.isPending}>
            {confirm.isPending ? t("twofa.verifying") : t("twofa.confirm")}
          </button>
        </div>
      </form>
    );
  }

  const action = enabled ? disable : begin;
  return (
    <form
      key="password"
      className="card form"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        setDone(null);
        action.mutate();
      }}
    >
      {done && <Notice>{done === "on" ? t("twofa.nowOn") : t("twofa.nowOff")}</Notice>}
      <ErrorAlert error={action.error} />
      <p className="muted">{enabled ? t("twofa.on", { email: user.email }) : t("twofa.off")}</p>
      <label>
        {t("twofa.password")}
        <PasswordInput
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            if (action.isError) action.reset();
          }}
          autoComplete="current-password"
          required
        />
      </label>
      <div className="actions">
        <button
          type="submit"
          className={enabled ? "button button-ghost button-danger" : "button"}
          disabled={action.isPending || !password}
        >
          {action.isPending && !enabled
            ? t("twofa.sending")
            : enabled
              ? t("twofa.turnOff")
              : t("twofa.turnOn")}
        </button>
      </div>
    </form>
  );
}

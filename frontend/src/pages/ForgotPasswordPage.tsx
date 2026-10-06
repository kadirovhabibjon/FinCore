import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import * as api from "../api/endpoints";
import { ErrorAlert, Notice } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useI18n } from "../i18n";

/** Forgot password, in two steps on one page: say whose account it is
 * (a code is emailed to that account's address), then enter the code
 * with a new password. Knowing a phone number is not enough to change a
 * password; reading the account's mailbox is. */
export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { t, tr } = useI18n();
  const [identifier, setIdentifier] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mismatch, setMismatch] = useState(false);

  async function sendCode() {
    setSubmitting(true);
    setError(null);
    try {
      await api.requestPasswordReset(identifier);
      setCodeSent(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setSubmitting(false);
    }
  }

  async function onRequest(event: FormEvent) {
    event.preventDefault();
    await sendCode();
  }

  async function onConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    // Same reason as on registration: a typo in a password nobody can
    // see would lock the account out again.
    if (form.get("new_password") !== form.get("confirm_password")) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setSubmitting(true);
    setError(null);
    try {
      await api.confirmPasswordReset(
        identifier,
        String(form.get("code")).trim(),
        String(form.get("new_password")),
      );
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }

  if (!codeSent) {
    return (
      <div className="auth-page">
        <LanguageSwitch className="auth-lang" />
        {/* Keyed: without it React reuses the first step's input for the code
            field, leaving the phone number typed there in it. */}
        <form key="request" className="card auth-card" onSubmit={onRequest}>
          <h1>{t("forgot.title")}</h1>
          <p className="muted">{t("forgot.intro")}</p>
          <ErrorAlert error={error} />
          <label>
            {t("common.phoneOrEmail")}
            <input
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              type="text"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="+998 90 123 45 67"
              required
            />
          </label>
          <button type="submit" className="button" disabled={submitting}>
            {submitting ? t("forgot.sending") : t("forgot.send")}
          </button>
          <p className="muted">
            {t("forgot.remembered")} <Link to="/login">{t("forgot.back")}</Link>
          </p>
        </form>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <LanguageSwitch className="auth-lang" />
      <form key="confirm" className="card auth-card" onSubmit={onConfirm}>
        <h1>{t("forgot.newTitle")}</h1>
        <Notice>{tr("forgot.sent", { account: <strong>{identifier.trim()}</strong> })}</Notice>
        <ErrorAlert error={error} />
        <label>
          {t("forgot.code")}
          <input
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="123456"
            title={t("forgot.codeHint")}
            required
          />
        </label>
        <label>
          {t("forgot.newPassword")}
          <PasswordInput name="new_password" autoComplete="new-password" required minLength={8} />
        </label>
        <label>
          {t("forgot.confirm")}
          <PasswordInput
            name="confirm_password"
            autoComplete="new-password"
            required
            minLength={8}
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">{t("forgot.mismatch")}</span>}
        </label>
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? t("forgot.saving") : t("forgot.save")}
        </button>
        <p className="muted">
          {t("forgot.noEmail")}{" "}
          <button
            type="button"
            className="link-button"
            disabled={submitting}
            onClick={() => void sendCode()}
          >
            {t("forgot.resend")}
          </button>{" "}
          {t("forgot.or")}{" "}
          <button type="button" className="link-button" onClick={() => setCodeSent(false)}>
            {t("forgot.other")}
          </button>
          .
        </p>
      </form>
    </div>
  );
}

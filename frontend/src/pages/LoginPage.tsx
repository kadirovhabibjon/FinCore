import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

import type { TwoFactorChallenge } from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ErrorAlert, Notice } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useI18n } from "../i18n";

/** `admin` is the admin console's sign-in: same accounts and API, but
 * its own title and no self-registration (staff roles are granted by an
 * operator, ADR-0006). */
export function LoginPage({ admin = false }: { admin?: boolean }) {
  const { t } = useI18n();
  const { login, verifyLogin } = useAuth();
  // Set once the password was right on an account with two-step
  // sign-in: the page then asks for the emailed code instead.
  const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null);
  const location = useLocation();
  const state = location.state as { registered?: boolean; passwordReset?: boolean } | null;
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
      // On success RedirectIfAuthenticated moves the user on; this
      // component unmounts, so there is no state left to reset.
      const pending = await login(String(form.get("identifier")), String(form.get("password")));
      if (pending) {
        setChallenge(pending);
        setSubmitting(false);
      }
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }

  async function onVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge) return;
    const code = String(new FormData(event.currentTarget).get("code")).trim();
    setSubmitting(true);
    setError(null);
    try {
      await verifyLogin(challenge.challenge_id, code);
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }

  if (challenge) {
    return (
      <div className="auth-page">
        <LanguageSwitch className="auth-lang" />
        {/* Keyed: without it React reuses the password form's inputs. */}
        <form key="code" className="card auth-card" onSubmit={onVerify}>
          <h1>{t("twofa.codeTitle")}</h1>
          <Notice>{t("twofa.codeSent", { email: challenge.email_hint })}</Notice>
          <ErrorAlert error={error} />
          <label>
            {t("twofa.code")}
            <input
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              placeholder="000000"
              required
              autoFocus
            />
          </label>
          <button type="submit" className="button" disabled={submitting}>
            {submitting ? t("twofa.verifying") : t("twofa.verify")}
          </button>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => {
              // A code that failed is gone; the password step makes a new one.
              setChallenge(null);
              setError(null);
            }}
          >
            {t("twofa.back")}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <LanguageSwitch className="auth-lang" />
      <form key="password" className="card auth-card" onSubmit={onSubmit}>
        <h1>{admin ? t("admin.login.title") : t("login.title")}</h1>
        {admin && <p className="muted">{t("admin.login.note")}</p>}
        {state?.registered && <Notice>{t("login.registered")}</Notice>}
        {state?.passwordReset && (
          <Notice>{t("login.passwordReset")}</Notice>
        )}
        <ErrorAlert error={error} />
        <label>
          {t("common.phoneOrEmail")}
          <input
            name="identifier"
            type="text"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="+998 90 123 45 67"
            required
          />
        </label>
        <label>
          {t("common.password")}
          <PasswordInput name="password" autoComplete="current-password" required />
        </label>
        {!admin && (
          <p className="forgot-link">
            <Link to="/forgot-password">{t("login.forgot")}</Link>
          </p>
        )}
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? t("login.submitting") : t("common.signIn")}
        </button>
        {!admin && (
          <p className="muted">
            {t("login.newHere")} <Link to="/register">{t("login.createAccount")}</Link>
          </p>
        )}
      </form>
    </div>
  );
}

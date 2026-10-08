import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

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
  const { login } = useAuth();
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
      await login(String(form.get("identifier")), String(form.get("password")));
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <LanguageSwitch className="auth-lang" />
      <form className="card auth-card" onSubmit={onSubmit}>
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

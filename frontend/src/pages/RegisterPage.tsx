import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import * as api from "../api/endpoints";
import { ErrorAlert } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { useI18n } from "../i18n";

export function RegisterPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mismatch, setMismatch] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    // Checked here, not by the API: a typo in a password nobody can see
    // would otherwise lock the new account out on its first sign-in.
    if (form.get("password") !== form.get("confirm_password")) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setSubmitting(true);
    setError(null);
    try {
      await api.register({
        email: String(form.get("email")),
        phone: String(form.get("phone")),
        password: String(form.get("password")),
        first_name: String(form.get("first_name")),
        last_name: String(form.get("last_name")),
      });
      navigate("/login", { replace: true, state: { registered: true } });
    } catch (caught) {
      setError(caught);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <LanguageSwitch className="auth-lang" />
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>{t("register.title")}</h1>
        <ErrorAlert error={error} />
        <div className="row">
          <label>
            {t("common.firstName")}
            <input name="first_name" autoComplete="given-name" required maxLength={100} />
          </label>
          <label>
            {t("common.lastName")}
            <input name="last_name" autoComplete="family-name" required maxLength={100} />
          </label>
        </div>
        <label>
          {t("common.email")}
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          {t("register.phone")}
          <input
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+998 90 123 45 67"
            required
          />
        </label>
        <label>
          {t("common.password")}
          <PasswordInput
            name="password"
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          {t("register.repeatPassword")}
          <PasswordInput
            name="confirm_password"
            autoComplete="new-password"
            required
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">{t("register.mismatch")}</span>}
        </label>
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? t("register.submitting") : t("register.submit")}
        </button>
        <p className="muted">
          {t("register.already")} <Link to="/login">{t("common.signIn")}</Link>
        </p>
      </form>
    </div>
  );
}

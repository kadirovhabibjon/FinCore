import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import * as api from "../api/endpoints";
import { ErrorAlert } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";

export function RegisterPage() {
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
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>Create your account</h1>
        <ErrorAlert error={error} />
        <div className="row">
          <label>
            First name
            <input name="first_name" autoComplete="given-name" required maxLength={100} />
          </label>
          <label>
            Last name
            <input name="last_name" autoComplete="family-name" required maxLength={100} />
          </label>
        </div>
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          Phone
          <input
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+998 90 123 45 67"
            required
          />
        </label>
        <label>
          Password
          <PasswordInput
            name="password"
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>
        <label>
          Repeat password
          <PasswordInput
            name="confirm_password"
            autoComplete="new-password"
            required
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">The two passwords differ.</span>}
        </label>
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Creating…" : "Create account"}
        </button>
        <p className="muted">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}

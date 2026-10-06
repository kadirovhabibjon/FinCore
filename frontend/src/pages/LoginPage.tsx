import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../auth/context";
import { ErrorAlert, Notice } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";

/** `admin` is the admin console's sign-in: same accounts and API, but
 * its own title and no self-registration (staff roles are granted by an
 * operator, ADR-0006). */
export function LoginPage({ admin = false }: { admin?: boolean }) {
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
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>{admin ? "FinCore Admin" : "Sign in to FinCore"}</h1>
        {admin && <p className="muted">Staff sign-in. Customer accounts can't use this console.</p>}
        {state?.registered && <Notice>Account created. Sign in to continue.</Notice>}
        {state?.passwordReset && (
          <Notice>Password changed. Sign in with your new password.</Notice>
        )}
        <ErrorAlert error={error} />
        <label>
          Phone number or email
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
          Password
          <PasswordInput name="password" autoComplete="current-password" required />
        </label>
        {!admin && (
          <p className="forgot-link">
            <Link to="/forgot-password">Forgot password?</Link>
          </p>
        )}
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        {!admin && (
          <p className="muted">
            New here? <Link to="/register">Create an account</Link>
          </p>
        )}
      </form>
    </div>
  );
}

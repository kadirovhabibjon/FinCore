import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../auth/context";
import { ErrorAlert, Notice } from "../components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const location = useLocation();
  const state = location.state as { registered?: boolean } | null;
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
      await login(String(form.get("email")), String(form.get("password")));
    } catch (caught) {
      setError(caught);
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>Sign in to FinCore</h1>
        {state?.registered && <Notice>Account created. Sign in to continue.</Notice>}
        <ErrorAlert error={error} />
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </div>
  );
}

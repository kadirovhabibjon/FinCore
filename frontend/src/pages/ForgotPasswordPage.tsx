import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import * as api from "../api/endpoints";
import { ErrorAlert, Notice } from "../components/ui";
import { PasswordInput } from "../components/PasswordInput";

/** Forgot password, in two steps on one page: say whose account it is
 * (a code is emailed to that account's address), then enter the code
 * with a new password. Knowing a phone number is not enough to change a
 * password; reading the account's mailbox is. */
export function ForgotPasswordPage() {
  const navigate = useNavigate();
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
        {/* Keyed: without it React reuses the first step's input for the code
            field, leaving the phone number typed there in it. */}
        <form key="request" className="card auth-card" onSubmit={onRequest}>
          <h1>Reset your password</h1>
          <p className="muted">
            Enter your phone number or email. We&apos;ll send a 6-digit code to the email address
            of your account.
          </p>
          <ErrorAlert error={error} />
          <label>
            Phone number or email
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
            {submitting ? "Sending…" : "Send code"}
          </button>
          <p className="muted">
            Remembered it? <Link to="/login">Back to sign in</Link>
          </p>
        </form>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <form key="confirm" className="card auth-card" onSubmit={onConfirm}>
        <h1>Set a new password</h1>
        <Notice>
          If <strong>{identifier.trim()}</strong> has a FinCore account, a code is on its way to
          that account&apos;s email. It works for 10 minutes.
        </Notice>
        <ErrorAlert error={error} />
        <label>
          Code from the email
          <input
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="123456"
            title="The 6 digits from the email"
            required
          />
        </label>
        <label>
          New password
          <PasswordInput name="new_password" autoComplete="new-password" required minLength={8} />
        </label>
        <label>
          Confirm new password
          <PasswordInput
            name="confirm_password"
            autoComplete="new-password"
            required
            minLength={8}
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">The passwords don&apos;t match.</span>}
        </label>
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? "Saving…" : "Save new password"}
        </button>
        <p className="muted">
          No email?{" "}
          <button
            type="button"
            className="link-button"
            disabled={submitting}
            onClick={() => void sendCode()}
          >
            Send a new code
          </button>{" "}
          or{" "}
          <button type="button" className="link-button" onClick={() => setCodeSent(false)}>
            use a different account
          </button>
          .
        </p>
      </form>
    </div>
  );
}

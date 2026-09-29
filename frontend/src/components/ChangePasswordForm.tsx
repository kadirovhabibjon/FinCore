import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { ErrorAlert, Notice } from "./ui";

export function ChangePasswordForm() {
  const queryClient = useQueryClient();
  const [mismatch, setMismatch] = useState(false);
  const change = useMutation({
    mutationFn: api.changePassword,
    // Every other session was just revoked; show the list without them.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const next = String(data.get("new_password"));
    if (next !== String(data.get("confirm_password"))) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    change.mutate(
      { current_password: String(data.get("current_password")), new_password: next },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      {change.isSuccess && (
        <Notice>Password changed. Every other device has been signed out.</Notice>
      )}
      <ErrorAlert error={change.error} />
      <label>
        Current password
        <input
          name="current_password"
          type="password"
          autoComplete="current-password"
          required
        />
      </label>
      <div className="row">
        <label>
          New password
          <input
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
          />
        </label>
        <label>
          Repeat new password
          <input
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            required
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">The two new passwords differ.</span>}
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="button" disabled={change.isPending}>
          {change.isPending ? "Changing…" : "Change password"}
        </button>
      </div>
    </form>
  );
}

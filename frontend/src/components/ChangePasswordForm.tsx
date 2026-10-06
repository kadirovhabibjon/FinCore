import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { ErrorAlert, Notice } from "./ui";
import { PasswordInput } from "./PasswordInput";
import { useI18n } from "../i18n";

export function ChangePasswordForm() {
  const { t } = useI18n();
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
        <Notice>{t("password.changed")}</Notice>
      )}
      <ErrorAlert error={change.error} />
      <label>
        {t("password.current")}
        <PasswordInput
          name="current_password"
          autoComplete="current-password"
          required
        />
      </label>
      <div className="row">
        <label>
          {t("password.new")}
          <PasswordInput
            name="new_password"
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
          />
        </label>
        <label>
          {t("password.repeat")}
          <PasswordInput
            name="confirm_password"
            autoComplete="new-password"
            required
            aria-invalid={mismatch}
          />
          {mismatch && <span className="field-error">{t("password.mismatch")}</span>}
        </label>
      </div>
      <div className="actions">
        <button type="submit" className="button" disabled={change.isPending}>
          {change.isPending ? t("password.changing") : t("password.change")}
        </button>
      </div>
    </form>
  );
}

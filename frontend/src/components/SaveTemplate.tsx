import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { ErrorAlert, Notice } from "./ui";

/** After a payment or a transfer: keep it to make again. Asks only for
 * a name, and whether the amount belongs to the template. */
export function SaveTemplate({
  suggestedName,
  what,
  amount,
  amountText,
}: {
  suggestedName: string;
  /** What is saved, without the name and the amount. */
  what:
    | { kind: "SERVICE"; service_code: string; account: string }
    | { kind: "TRANSFER"; card_number: string };
  /** The amount just paid, as the decimal string that was sent. */
  amount: string;
  /** The same, as shown to the customer: "50,000.00 UZS". */
  amountText: string;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(suggestedName);
  const [withAmount, setWithAmount] = useState(true);
  const save = useMutation({
    mutationFn: () =>
      api.saveTemplate({ ...what, name: name.trim(), amount: withAmount ? amount : null }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  if (save.isSuccess) return <Notice>{t("tpl.saved")}</Notice>;
  if (!open) {
    return (
      <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
        {t("tpl.save")}
      </button>
    );
  }
  return (
    <form
      className="card form save-template"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        if (name.trim()) save.mutate();
      }}
    >
      <ErrorAlert error={save.error} />
      <label>
        {t("tpl.name")}
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={60}
          required
          autoFocus
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={withAmount}
          onChange={(event) => setWithAmount(event.target.checked)}
        />
        {t("tpl.withAmount", { amount: amountText })}
      </label>
      <div className="actions">
        <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
          {t("tpl.cancel")}
        </button>
        <button type="submit" className="button" disabled={save.isPending || !name.trim()}>
          {save.isPending ? t("tpl.saving") : t("tpl.saveButton")}
        </button>
      </div>
    </form>
  );
}

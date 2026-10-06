import type { ReactNode } from "react";

import { StatusBadge } from "./ui";
import { useI18n, type MessageKey } from "../i18n";
import { reasonText } from "../lib/reasons";

// What each saga state means to the person who just started it
// (spec Sections 10.1 and 11). The API call itself succeeded in every
// case; these are the business outcomes it can land on.
const EXPLANATIONS: Record<string, MessageKey> = {
  COMPLETED: "outcome.COMPLETED",
  SUCCESS: "outcome.SUCCESS",
  FAILED: "outcome.FAILED",
  PENDING: "outcome.PENDING",
  CREATED: "outcome.PENDING",
  PROCESSING: "outcome.PROCESSING",
};

export function OperationOutcome({
  kind,
  status,
  failureReason,
  reference,
  amount,
}: {
  kind: string;
  status: string;
  failureReason?: string | null;
  reference: string;
  amount: ReactNode;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const explanation = EXPLANATIONS[status];
  const tone = status === "FAILED" ? "alert-error" : "alert-info";
  return (
    <div className={`card outcome alert ${tone}`} role="status">
      <div className="outcome-head">
        <strong>
          {kind} {reference}
        </strong>
        <StatusBadge status={status} />
      </div>
      <div className="outcome-amount">{amount}</div>
      <p>{explanation ? t(explanation) : status}</p>
      {failureReason && <p className="muted">{t("outcome.reason", { reason: reasonText(failureReason, i18n) })}</p>}
    </div>
  );
}

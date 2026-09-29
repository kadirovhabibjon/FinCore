import type { ReactNode } from "react";

import { StatusBadge } from "./ui";

// What each saga state means to the person who just started it
// (spec Sections 10.1 and 11). The API call itself succeeded in every
// case; these are the business outcomes it can land on.
const EXPLANATIONS: Record<string, string> = {
  COMPLETED: "The money has moved.",
  SUCCESS: "The payment went through.",
  FAILED: "It did not go through and no money moved.",
  PENDING: "It is waiting for a manual fraud review. You will see the result in your history.",
  CREATED: "It is waiting for a manual fraud review. You will see the result in your history.",
  PROCESSING:
    "It is being settled. The outcome was not confirmed yet; it will resolve on its own shortly.",
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
      <p>{EXPLANATIONS[status] ?? status}</p>
      {failureReason && <p className="muted">Reason: {failureReason}</p>}
    </div>
  );
}

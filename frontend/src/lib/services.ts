// Paying service providers: the same checks the server makes on the
// account a payment is for (payment-service's billers.clean_account),
// made here first so a typo is caught in the form.
import type { Service } from "../api/endpoints";

export const CATEGORY_ORDER = ["MOBILE", "INTERNET", "UTILITIES", "TV"] as const;

/** Whether `raw` is the kind of account this provider identifies a customer by. */
export function isValidAccount(kind: Service["account_kind"], raw: string): boolean {
  const text = raw.trim();
  if (kind === "PHONE") {
    let digits = text.replace(/\D/g, "");
    if (digits.length === 12 && digits.startsWith("998")) digits = digits.slice(3);
    return digits.length === 9;
  }
  if (kind === "ACCOUNT_NUMBER") return /^[0-9]{6,14}$/.test(text.replace(/[\s-]/g, ""));
  return /^[A-Za-z0-9._-]{4,32}$/.test(text);
}

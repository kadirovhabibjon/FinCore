// ADR-0001 on the client: amounts arrive as integer minor units and
// leave as decimal strings. Nothing here ever does float arithmetic on
// money — formatting splits the integer with BigInt, and input is
// validated as a string and sent to the API as that same string.

import { i18n } from "../i18n";
import { formatCardNumber } from "./card";

// Mirrors fincore-common's SUPPORTED_CURRENCIES.
export const CURRENCY_EXPONENTS: Readonly<Record<string, number>> = { UZS: 2, USD: 2 };
export const SUPPORTED_CURRENCIES = Object.keys(CURRENCY_EXPONENTS);

function exponentOf(currency: string): number {
  const exponent = CURRENCY_EXPONENTS[currency];
  if (exponent === undefined) throw new Error(`unsupported currency ${currency}`);
  return exponent;
}

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** 123456 UZS -> "1,234.56 UZS" */
export function formatMinor(amountMinor: number, currency: string): string {
  const exponent = exponentOf(currency);
  const value = BigInt(amountMinor);
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(exponent + 1, "0");
  const whole = digits.slice(0, digits.length - exponent);
  const fraction = exponent > 0 ? `.${digits.slice(digits.length - exponent)}` : "";
  return `${negative ? "-" : ""}${groupThousands(whole)}${fraction} ${currency}`;
}

/** A wallet as one line of text, for <option>s:
 * "UZS · 9955 1234 5678 9011 · 1,000.00 UZS available", led by the
 * owner's name for it when it has one and ending in "blocked" when the
 * owner has blocked it. */
export function walletLabel(wallet: {
  card_number: string;
  currency: string;
  balance_minor: number;
  held_minor: number;
  name?: string | null;
  blocked?: boolean;
}): string {
  const available = formatMinor(wallet.balance_minor - wallet.held_minor, wallet.currency);
  const label = i18n().t("wallet.label", {
    currency: wallet.name ? `${wallet.name} · ${wallet.currency}` : wallet.currency,
    card: formatCardNumber(wallet.card_number),
    amount: available,
  });
  return wallet.blocked ? i18n().t("card.labelBlocked", { label }) : label;
}

/** A valid amount string as integer minor units: "12.5" UZS -> 1250.
 * Digits only, no float arithmetic. Call after `validateAmount`. */
export function toMinor(value: string, currency: string): number {
  const exponent = exponentOf(currency);
  const [whole = "0", fraction = ""] = value.trim().split(".");
  return Number(BigInt(whole + fraction.padEnd(exponent, "0").slice(0, exponent)));
}

/**
 * Returns an error message (in the language the site is showing), or
 * null when `value` is a positive decimal
 * with no more precision than the currency has — the same rule the
 * backend enforces, checked here only to fail fast in the form.
 */
export function validateAmount(value: string, currency: string): string | null {
  const exponent = exponentOf(currency);
  const pattern = exponent > 0 ? new RegExp(`^\\d+(\\.\\d{1,${exponent}})?$`) : /^\d+$/;
  const trimmed = value.trim();
  if (!pattern.test(trimmed)) {
    return exponent > 0
      ? i18n().t("amount.format", { decimals: exponent })
      : i18n().t("amount.whole");
  }
  if (/^[0.]+$/.test(trimmed)) return i18n().t("amount.positive");
  return null;
}

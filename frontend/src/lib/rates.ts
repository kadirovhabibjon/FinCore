// Exchange-rate arithmetic for the reference widget. These are floats on
// purpose: the result is an estimate shown to the customer, never an
// amount that is sent to the API or posted to a ledger (ADR-0001 covers
// those, in integer minor units).

/** Converts between two currencies given units-per-USD rates. */
export function convert(
  amount: number,
  from: string,
  to: string,
  rates: Readonly<Record<string, number>>,
): number | null {
  const fromRate = rates[from];
  const toRate = rates[to];
  if (fromRate === undefined || toRate === undefined || !Number.isFinite(amount)) return null;
  return (amount / fromRate) * toRate;
}

/** "1,234.5" / "1 234,5" -> 1234.5; null when it isn't a non-negative number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[\s,](?=\d{3}(\D|$))/g, "").replace(",", ".").trim();
  if (!/^\d+(\.\d*)?$|^\.\d+$/.test(cleaned)) return null;
  return Number(cleaned);
}

/** Two decimals for everyday amounts, more for values below one. */
export function formatRate(value: number): string {
  const digits = value >= 1 ? 2 : value >= 0.01 ? 4 : 6;
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

const names =
  typeof Intl.DisplayNames === "function"
    ? new Intl.DisplayNames(["en"], { type: "currency" })
    : null;

/** "UZS" -> "Uzbekistani Som"; the code itself when the name is unknown. */
export function currencyName(code: string): string {
  try {
    return names?.of(code) ?? code;
  } catch {
    return code;
  }
}

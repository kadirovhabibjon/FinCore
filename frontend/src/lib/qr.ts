// What a FinCore QR code says: a link to the Send page with the card
// filled in. A link rather than the bare number, so a phone's own camera
// app opens FinCore straight on the right page; the scanner inside
// FinCore reads the same code.
import { cardDigits, isValidCardNumber } from "./card";

/** The link a wallet's QR code encodes. */
export function receiveLink(origin: string, cardNumber: string): string {
  return `${origin}/transfer?to=${cardNumber}`;
}

/** The card number in something a scanner read: a FinCore receive link
 * (from any host - the card is what matters, and it is looked up before
 * anything is sent) or the 16 digits on their own. Null for anything
 * else, including a card number that fails its check digit. */
export function cardFromScan(text: string): string | null {
  const value = text.trim();
  let candidate = value;
  try {
    const url = new URL(value);
    candidate = url.searchParams.get("to") ?? "";
  } catch {
    // Not a link: maybe the digits themselves.
  }
  if (!/^[\d\s-]{16,23}$/.test(candidate)) return null;
  const digits = cardDigits(candidate);
  return isValidCardNumber(digits) ? digits : null;
}

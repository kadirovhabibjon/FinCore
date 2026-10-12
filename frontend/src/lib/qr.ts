// What a FinCore QR code says: a link to the Send page with the card
// filled in. A link rather than the bare number, so a phone's own camera
// app opens FinCore straight on the right page; the scanner inside
// FinCore reads the same code.
import { cardDigits, isValidCardNumber } from "./card";

/** The link a wallet's QR code encodes. */
export function receiveLink(origin: string, cardNumber: string): string {
  return `${origin}/transfer?to=${cardNumber}`;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;

/** The link a merchant's QR code encodes: the Pay page with the
 * merchant filled in and, if the merchant wants, an amount. */
export function merchantLink(origin: string, merchantId: string, amount = ""): string {
  const query = new URLSearchParams({ merchant: merchantId });
  if (AMOUNT.test(amount.trim())) query.set("amount", amount.trim());
  return `${origin}/pay/merchant?${query.toString()}`;
}

/** The merchant, and the amount if one was asked for, in something a
 * scanner read: a FinCore pay link (from any host - the merchant is
 * looked up, and the customer still presses Pay) or a bare merchant
 * id. Null for anything else. An amount that isn't a plain number is
 * dropped rather than trusted. */
export function merchantFromScan(text: string): { merchantId: string; amount: string } | null {
  const value = text.trim();
  let merchantId = value;
  let amount = "";
  try {
    const url = new URL(value);
    merchantId = url.searchParams.get("merchant") ?? "";
    amount = url.searchParams.get("amount") ?? "";
  } catch {
    // Not a link: maybe the id itself.
  }
  if (!UUID.test(merchantId)) return null;
  return { merchantId: merchantId.toLowerCase(), amount: AMOUNT.test(amount) ? amount : "" };
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

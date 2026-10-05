// FinCore card numbers on the client: formatting and a check that
// catches typos before asking the server. Mirrors fincore_common's
// card_number.py; the server validates again and is the authority.

export const CARD_NUMBER_LENGTH = 16;
const CARD_NUMBER_PREFIX = "9955";

/** The digits of whatever was typed or pasted, at most 16 of them. */
export function cardDigits(text: string): string {
  return text.replace(/\D/g, "").slice(0, CARD_NUMBER_LENGTH);
}

/** "9955123456789011" -> "9955 1234 5678 9011" (works on partial input). */
export function formatCardNumber(digits: string): string {
  return digits.replace(/(.{4})(?=.)/g, "$1 ");
}

function luhnCheckDigit(payload: string): number {
  let total = 0;
  [...payload].reverse().forEach((char, index) => {
    let digit = Number(char);
    if (index % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  });
  return (10 - (total % 10)) % 10;
}

export function isValidCardNumber(digits: string): boolean {
  return (
    /^\d{16}$/.test(digits) &&
    digits.startsWith(CARD_NUMBER_PREFIX) &&
    luhnCheckDigit(digits.slice(0, -1)) === Number(digits.slice(-1))
  );
}

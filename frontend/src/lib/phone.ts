// Phone numbers as the Send page needs them: enough to know when a
// number is complete and worth looking up. The server (identity-
// service's normalize_phone) is what decides what a number really is;
// this mirrors its rules so a half-typed number is never sent.

const UZBEKISTAN = "998";
const LOCAL_LENGTH = 9; // 90 123 45 67

/** The digits of what was typed, without a leading "00" (which counts as "+"). */
export function phoneDigits(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  return raw.trim().startsWith("00") ? digits.slice(2) : digits;
}

/** A whole number: 9 digits (taken as Uzbek), +998 and 9 digits, or
 * another country's 8 to 15 digits. */
export function isCompletePhone(raw: string): boolean {
  const digits = phoneDigits(raw);
  if (digits.length === LOCAL_LENGTH) return true;
  if (digits.startsWith(UZBEKISTAN)) return digits.length === UZBEKISTAN.length + LOCAL_LENGTH;
  return digits.length >= 8 && digits.length <= 15;
}

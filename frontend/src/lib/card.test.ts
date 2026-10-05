import { describe, expect, it } from "vitest";

import { cardDigits, formatCardNumber, isValidCardNumber } from "./card";

describe("card numbers", () => {
  it("keeps only digits, sixteen at most", () => {
    expect(cardDigits("9955 1234-5678 9011")).toBe("9955123456789011");
    expect(cardDigits("9955123456789011999")).toBe("9955123456789011");
    expect(cardDigits("abc")).toBe("");
  });

  it("groups digits in fours while typing", () => {
    expect(formatCardNumber("9955")).toBe("9955");
    expect(formatCardNumber("99551")).toBe("9955 1");
    expect(formatCardNumber("9955123456789011")).toBe("9955 1234 5678 9011");
  });

  it("accepts a FinCore number and catches a typo", () => {
    expect(isValidCardNumber("9955123456789011")).toBe(true);
    expect(isValidCardNumber("9955123456789012")).toBe(false);
    expect(isValidCardNumber("995512345678901")).toBe(false);
    // A real card network's number passes Luhn but isn't FinCore's.
    expect(isValidCardNumber("4111111111111111")).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import { convert, currencyName, formatRate, parseAmount } from "./rates";

const RATES = { USD: 1, UZS: 12_000, EUR: 0.8 };

describe("convert", () => {
  it("goes through the dollar for any pair", () => {
    expect(convert(100, "USD", "UZS", RATES)).toBe(1_200_000);
    expect(convert(8, "EUR", "UZS", RATES)).toBe(120_000);
    expect(convert(24_000, "UZS", "USD", RATES)).toBe(2);
  });

  it("returns null for a currency without a rate", () => {
    expect(convert(1, "USD", "XXX", RATES)).toBeNull();
  });
});

describe("parseAmount", () => {
  it("accepts the common ways of writing a number", () => {
    expect(parseAmount("1500")).toBe(1500);
    expect(parseAmount("1,500.25")).toBe(1500.25);
    expect(parseAmount("1 500,5")).toBe(1500.5);
    expect(parseAmount("0,5")).toBe(0.5);
  });

  it("rejects anything else", () => {
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("-5")).toBeNull();
    expect(parseAmount("abc")).toBeNull();
  });
});

describe("formatting", () => {
  it("keeps small rates readable", () => {
    expect(formatRate(12_000.456)).toBe("12,000.46");
    expect(formatRate(0.0000833)).toBe("0.000083");
  });

  it("names currencies", () => {
    expect(currencyName("USD")).toBe("US Dollar");
  });
});

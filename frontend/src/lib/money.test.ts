import { describe, expect, it } from "vitest";

import { formatMinor, minorToInput, validateAmount, walletLabel } from "./money";

describe("formatMinor", () => {
  it.each([
    [0, "0.00 UZS"],
    [5, "0.05 UZS"],
    [100, "1.00 UZS"],
    [123_456, "1,234.56 UZS"],
    [-250, "-2.50 UZS"],
    [100_000_000_000_01, "100,000,000,000.01 UZS"],
  ])("formats %d minor units exactly", (minor, expected) => {
    expect(formatMinor(minor, "UZS")).toBe(expected);
  });

  it("writes amounts the local way in Uzbek and Russian", () => {
    expect(formatMinor(182_000_000, "UZS", "uz")).toBe("1\u00a0820\u00a0000,00 so‘m");
    expect(formatMinor(182_000_000, "UZS", "ru")).toBe("1\u00a0820\u00a0000,00 сум");
    expect(formatMinor(-1_696, "USD", "uz")).toBe("-16,96 USD");
    expect(formatMinor(123_456, "UZS", "en")).toBe("1,234.56 UZS");
  });

  it("rejects currencies the backend doesn't support", () => {
    expect(() => formatMinor(1, "EUR")).toThrow("unsupported currency EUR");
  });
});

it("fills an amount field the same in every language", () => {
  expect(minorToInput(5_000_000, "UZS")).toBe("50000.00");
  expect(minorToInput(5, "USD")).toBe("0.05");
});

describe("validateAmount", () => {
  it.each(["1", "100", "100.5", "100.50", " 7.25 "])("accepts %j", (value) => {
    expect(validateAmount(value, "USD")).toBeNull();
  });

  it.each(["", "abc", "1.005", "-5", "1e3", "1,000", ".5"])("rejects %j", (value) => {
    expect(validateAmount(value, "USD")).toMatch(/amount like/);
  });

  it.each(["0", "0.00", "00.0"])("rejects zero (%j)", (value) => {
    expect(validateAmount(value, "USD")).toBe("Amount must be greater than zero.");
  });
});

it("labels a wallet by its card number and available balance", () => {
  expect(
    walletLabel({
      card_number: "9955123456789011",
      currency: "USD",
      balance_minor: 10_000,
      held_minor: 2_500,
    }),
  ).toBe("USD · 9955 1234 5678 9011 · 75.00 USD available");
});

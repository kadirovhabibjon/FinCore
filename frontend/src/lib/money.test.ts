import { describe, expect, it } from "vitest";

import { formatMinor, validateAmount, walletLabel } from "./money";

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

  it("rejects currencies the backend doesn't support", () => {
    expect(() => formatMinor(1, "EUR")).toThrow("unsupported currency EUR");
  });
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

it("labels a wallet by its available balance", () => {
  expect(
    walletLabel({ id: "abcdef12-0000", currency: "USD", balance_minor: 10_000, held_minor: 2_500 }),
  ).toBe("USD · abcdef12 · 75.00 USD available");
});

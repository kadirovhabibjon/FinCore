import { describe, expect, it } from "vitest";

import { cardFromScan, receiveLink } from "./qr";

const CARD = "9955123456789011";

describe("QR codes", () => {
  it("encodes a link to the Send page with the card filled in", () => {
    expect(receiveLink("https://fincore.example", CARD)).toBe(
      `https://fincore.example/transfer?to=${CARD}`,
    );
  });

  it("reads the card back from a link or from bare digits", () => {
    expect(cardFromScan(receiveLink("https://fincore.example", CARD))).toBe(CARD);
    expect(cardFromScan(`  http://localhost:8180/transfer?to=${CARD}&x=1 `)).toBe(CARD);
    expect(cardFromScan(CARD)).toBe(CARD);
    expect(cardFromScan("9955 1234 5678 9011")).toBe(CARD);
  });

  it("refuses anything that is not a FinCore card", () => {
    expect(cardFromScan("https://fincore.example/transfer")).toBeNull();
    expect(cardFromScan("https://fincore.example/transfer?to=9955123456789012")).toBeNull();
    expect(cardFromScan("https://evil.example/?to=javascript:alert(1)")).toBeNull();
    expect(cardFromScan("4111111111111111")).toBeNull();
    expect(cardFromScan("WIFI:S:home;T:WPA;P:secret;;")).toBeNull();
    expect(cardFromScan("")).toBeNull();
  });
});

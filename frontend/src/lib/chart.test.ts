import { describe, expect, it } from "vitest";

import { columnPath, compact, monthLabel, niceTicks } from "./chart";

describe("chart helpers", () => {
  it("picks round ticks that cover the largest value", () => {
    expect(niceTicks(1_250_000)).toEqual([0, 500_000, 1_000_000, 1_500_000]);
    expect(niceTicks(7)).toEqual([0, 2, 4, 6, 8]);
    expect(niceTicks(1000)).toEqual([0, 250, 500, 750, 1000]);
    expect(niceTicks(0.3).at(-1)).toBeGreaterThanOrEqual(0.3);
    expect(niceTicks(0)).toEqual([0, 1]);
  });

  it("labels the axis compactly", () => {
    expect(compact(1_500_000)).toBe("1.5M");
    expect(compact(25_000)).toBe("25K");
    expect(compact(1_000_000_000)).toBe("1B");
    expect(compact(950)).toBe("950");
    expect(compact(0)).toBe("0");
  });

  it("names months, with the year where a year begins", () => {
    expect(monthLabel("2026-10")).toBe("Oct");
    expect(monthLabel("2026-01")).toBe("Jan 2026");
    expect(monthLabel("2026-10", true)).toBe("Oct 2026");
  });

  it("draws nothing for a zero column and never rounds past its own size", () => {
    expect(columnPath(10, 100, 20, 0)).toBe("");
    expect(columnPath(10, 100, 20, 50)).toContain("Q10,50 14,50");
    // A 2px-tall column: the corner radius shrinks to fit.
    expect(columnPath(10, 100, 20, 2)).toContain("Q10,98 12,98");
  });
});

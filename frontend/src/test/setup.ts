import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { authTiming } from "../auth/tokenStore";
import { resetLang } from "../i18n";
import { resetTheme } from "../lib/theme";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // No real waiting between session-check and sign-out retries in tests.
  authTiming.retryDelaysMs = [0, 0, 0];
  authTiming.idleTimeoutMs = 15 * 60 * 1000;
  authTiming.idleCheckIntervalMs = 15_000;
  localStorage.clear();
  // Every test starts in the language a fresh visitor gets: English.
  resetLang();
  resetTheme();
});

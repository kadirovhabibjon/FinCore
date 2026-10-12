import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { authTiming } from "../auth/tokenStore";
import { resetLang } from "../i18n";
import { resetTheme } from "../lib/theme";

// How long findBy/waitFor keep looking. The default second is tight on
// a busy machine (a loaded laptop, a shared CI runner), where it turns
// into failures that have nothing to do with the code under test.
configure({ asyncUtilTimeout: 5000 });

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

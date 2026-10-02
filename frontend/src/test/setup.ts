import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { authTiming } from "../auth/tokenStore";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // No real waiting between session-check and sign-out retries in tests.
  authTiming.retryDelaysMs = [0, 0, 0];
  localStorage.clear();
});

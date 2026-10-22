import { defineConfig, devices } from "@playwright/test";

// Browser tests: the real web app in a real browser, against the whole
// stack running in docker compose (the same one tests/e2e talks to).
// They cover what neither vitest (a simulated DOM, a fake API) nor the
// API suite can see: routing and code-split pages loading for real, the
// CSP, layout at phone width, focus and keyboard use, accessibility.
export default defineConfig({
  testDir: "specs",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.FINCORE_URL ?? "http://localhost:8180",
    // Locally an installed Chrome will do (PW_CHANNEL=chrome); CI
    // installs Playwright's own Chromium.
    channel: process.env.PW_CHANNEL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL },
      testIgnore: /phone\.spec\.ts/,
    },
    {
      name: "phone",
      use: { ...devices["Pixel 7"], channel: process.env.PW_CHANNEL },
      testMatch: /phone\.spec\.ts/,
    },
  ],
});

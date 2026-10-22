import { test as base, expect, type Page } from "@playwright/test";

import type { Customer } from "./stack";

/** Signs in through the real sign-in form. */
export async function signIn(page: Page, customer: Customer): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Phone number or email").fill(customer.email);
  await page.getByLabel("Password", { exact: true }).fill(customer.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: `Hello, ${customer.firstName}` })).toBeVisible();
}

/** Every test also fails on anything the browser itself complains about:
 * a script error, a request the CSP blocked, a failed chunk load. */
export const test = base.extend<{ problems: string[] }>({
  problems: [
    async ({ page }, use) => {
      const problems: string[] = [];
      page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
      page.on("console", (message) => {
        const text = message.text();
        // A 401 from /auth/refresh is how a signed-out visit learns it is
        // signed out; the browser logs every failed request.
        if (message.type() === "error" && !/status of 401/.test(text)) {
          problems.push(`console: ${text}`);
        }
      });
      page.on("requestfailed", (request) => {
        if (!request.failure()?.errorText.includes("ERR_ABORTED")) {
          problems.push(`request failed: ${request.url()} ${request.failure()?.errorText}`);
        }
      });
      await use(problems);
      expect(problems, "the browser reported problems").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

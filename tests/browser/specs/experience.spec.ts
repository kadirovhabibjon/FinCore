import AxeBuilder from "@axe-core/playwright";

import { expect, signIn, test } from "../support/fixtures";
import { fund, newCustomer, openWallet } from "../support/stack";

test("the language and the theme are kept across a reload", async ({ page }) => {
  const customer = await newCustomer("Jasur");
  await fund(await openWallet(customer), 1_820_000_00);
  await signIn(page, customer);

  await page.getByLabel("Language").selectOption("uz");
  await expect(page.getByRole("heading", { name: "Salom, Jasur" })).toBeVisible();
  // Amounts read the local way in Uzbek.
  await expect(page.getByText("1 820 000,00 so‘m", { exact: true })).toBeVisible();

  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await page.locator(".topbar .theme-button").click();
  const chosen = await html.getAttribute("data-theme");
  expect(chosen).not.toBe(before);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Salom, Jasur" })).toBeVisible();
  await expect(html).toHaveAttribute("data-theme", chosen!);
});

test("a customer never downloads the admin console's code", async ({ page }) => {
  const scripts: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "script") scripts.push(request.url());
  });
  const customer = await newCustomer("Laylo");
  await openWallet(customer);
  await signIn(page, customer);
  // Pages beyond the home page arrive when first opened.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();

  expect(scripts.some((url) => /TransactionsPage-.*\.js/.test(url))).toBe(true);
  expect(scripts.filter((url) => /Admin/.test(url))).toEqual([]);
});

test("an address that doesn't exist says so inside the site", async ({ page }) => {
  const customer = await newCustomer();
  await signIn(page, customer);
  await page.goto("/no-such-page");
  await expect(page.getByRole("link", { name: /back/i })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
});

// Automated accessibility checks (axe-core, WCAG 2.1 A and AA) on the
// pages every customer uses. Serious and critical findings fail the test.
for (const [name, path] of [
  ["home", "/"],
  ["send", "/transfer"],
  ["pay", "/pay"],
  ["history", "/transactions"],
  ["statistics", "/stats"],
  ["settings", "/settings"],
] as const) {
  test(`the ${name} page has no serious accessibility problems`, async ({ page }) => {
    const customer = await newCustomer("Umida");
    await fund(await openWallet(customer), 10_000_00);
    await signIn(page, customer);
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    await page.waitForLoadState("networkidle");

    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = violations
      .filter((item) => item.impact === "serious" || item.impact === "critical")
      .map((item) => `${item.id}: ${item.help} (${item.nodes.map((node) => node.target.join(" ")).join(", ")})`);
    expect(serious).toEqual([]);
  });
}

test("the sign-in page has no serious accessibility problems", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to FinCore" })).toBeVisible();
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    violations
      .filter((item) => item.impact === "serious" || item.impact === "critical")
      .map((item) => item.id),
  ).toEqual([]);
});

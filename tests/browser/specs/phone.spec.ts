import { expect, signIn, test } from "../support/fixtures";
import { fund, newCustomer, openWallet } from "../support/stack";

// Run in the "phone" project only: a Pixel 7's screen, touch, user agent.

test("on a phone the menu is a tab bar and nothing is wider than the screen", async ({ page }) => {
  const customer = await newCustomer("Shahzod");
  await fund(await openWallet(customer), 5_000_00);
  await signIn(page, customer);

  const tabs = page.getByRole("navigation", { name: "Main" });
  const box = await tabs.boundingBox();
  const viewport = page.viewportSize()!;
  // Fixed to the bottom of the screen, within thumb reach.
  expect(box!.y + box!.height).toBeGreaterThan(viewport.height - 4);

  for (const path of ["/", "/transfer", "/pay", "/transactions", "/settings"]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(0);
  }

  await tabs.getByRole("link", { name: "Pay" }).tap();
  await expect(page.getByRole("heading", { name: "Payments" })).toBeVisible();
});

test("the chat button is a small round icon that still says what it is", async ({ page }) => {
  const customer = await newCustomer("Zarina");
  await openWallet(customer);
  await signIn(page, customer);

  const chat = page.getByRole("button", { name: "Ask FinCore" });
  await expect(chat).toBeVisible();
  const box = await chat.boundingBox();
  expect(Math.round(box!.width)).toBe(Math.round(box!.height));
  expect(box!.width).toBeLessThan(64);

  await chat.tap();
  await expect(page.getByRole("dialog")).toBeVisible();
});

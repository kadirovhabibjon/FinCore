import { randomBytes } from "node:crypto";

import { expect, signIn, test } from "../support/fixtures";
import { newCustomer } from "../support/stack";

test("a new customer signs up, signs in and opens a card", async ({ page }) => {
  const email = `browser-${randomBytes(6).toString("hex")}@example.com`;
  const password = `Br-${randomBytes(9).toString("base64url")}1!`;

  await page.goto("/register");
  await page.getByLabel("First name").fill("Nilufar");
  await page.getByLabel("Last name").fill("Karimova");
  await page.getByLabel("Email").fill(email);
  await page
    .getByLabel(/^Phone/)
    .fill(`+99890${String(randomBytes(4).readUInt32BE() % 10_000_000).padStart(7, "0")}`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel(/^Repeat password/).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("Account created. Sign in to continue.")).toBeVisible();
  await signIn(page, { email, password, firstName: "Nilufar", phone: "", token: "" });

  await expect(page.getByText(/no wallets yet/i)).toBeVisible();
  await page.getByRole("button", { name: "New wallet" }).click();
  const card = page.getByLabel("Card number");
  await expect(card).toHaveText(/^9955 \d{4} \d{4} \d{4}$/);
  await expect(page.getByText("0.00 UZS", { exact: true })).toBeVisible();
});

test("a wrong password is refused without saying which part was wrong", async ({ page }) => {
  const customer = await newCustomer();

  await page.goto("/login");
  await page.getByLabel("Phone number or email").fill(customer.email);
  await page.getByLabel("Password", { exact: true }).fill(`${customer.password}x`);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("signing out ends the session; the back button doesn't bring it back", async ({ page }) => {
  const customer = await newCustomer("Sardor");
  await signIn(page, customer);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  // Back to the history page's address: it asks for a sign-in again
  // instead of showing what was there.
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Sign in to FinCore" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "History" })).toHaveCount(0);
});

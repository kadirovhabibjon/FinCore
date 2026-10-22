import { expect, signIn, test } from "../support/fixtures";
import { balance, fund, newCustomer, openWallet } from "../support/stack";

test("sends money by card number, with the recipient named before anything moves", async ({
  page,
}) => {
  const sender = await newCustomer("Aziz");
  const recipient = await newCustomer("Madina", "Tursunova");
  const from = await openWallet(sender);
  const to = await openWallet(recipient);
  await fund(from, 50_000_00);
  await signIn(page, sender);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Send" }).click();
  await expect(page.getByRole("heading", { name: "Send money" })).toBeVisible();
  await page.getByLabel(/^To card number/).fill(to.card_number);
  // Who the money goes to is shown before Send is pressed.
  await expect(page.getByText("Madina T.")).toBeVisible();
  await page.getByLabel(/^Amount \(UZS\)/).fill("1250.50");
  await page.getByLabel("Note (optional)").fill("For lunch");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("The money has moved.")).toBeVisible();
  expect(await balance(sender, from)).toBe(50_000_00 - 1_250_50);
  expect(await balance(recipient, to)).toBe(1_250_50);

  // And it is in the history, opened from the top bar.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  const row = page.getByRole("row").filter({ hasText: "Madina T." });
  await expect(row).toContainText("1,250.50 UZS");
  await expect(row).toContainText("COMPLETED");
});

test("won't send more than the card holds, and says so before asking the server", async ({
  page,
}) => {
  const sender = await newCustomer("Aziz");
  const from = await openWallet(sender);
  const to = await openWallet(await newCustomer("Bobur"));
  await fund(from, 100_00);
  await signIn(page, sender);
  await page.goto("/transfer");

  await page.getByLabel(/^To card number/).fill(to.card_number);
  await page.getByLabel(/^Amount \(UZS\)/).fill("100.001");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/at most 2 decimals/)).toBeVisible();
  expect(await balance(sender, from)).toBe(100_00);
});

test("pays a mobile operator from the catalogue", async ({ page }) => {
  const customer = await newCustomer("Kamola");
  const wallet = await openWallet(customer);
  await fund(wallet, 200_000_00);
  await signIn(page, customer);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Pay" }).click();
  await page.getByRole("button", { name: "Beeline" }).click();
  await page.getByLabel(/^Phone number/).fill("+998901234567");
  await page.getByLabel(/^Amount \(UZS\)/).fill("25000");
  await page.getByRole("button", { name: "Pay", exact: true }).click();

  await expect(page.getByText("The payment went through.")).toBeVisible();
  expect(await balance(customer, wallet)).toBe(200_000_00 - 25_000_00);
});

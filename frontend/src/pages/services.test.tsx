import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../i18n";
import { isValidAccount } from "../lib/services";
import { WALLET, fakeApi, json, noLimit, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const service = (code: string, category: string, name: string, account_kind: string) => ({
  code,
  category,
  name,
  account_kind,
  currency: "UZS",
  min_amount_minor: 100_000,
  max_amount_minor: 500_000_000,
});
const SERVICES = [
  service("beeline", "MOBILE", "Beeline", "PHONE"),
  service("uzonline", "INTERNET", "Uzonline", "LOGIN"),
  service("electricity", "UTILITIES", "Electricity", "ACCOUNT_NUMBER"),
];
const USD = { ...WALLET, id: "99999999-0000-4000-8000-000000000003", currency: "USD" };

function paid(overrides: Record<string, unknown> = {}) {
  return json(
    {
      id: "55555555-5555-4555-8555-555555555555",
      reference: "PAY-SVC",
      source_wallet_id: WALLET.id,
      merchant_id: "66666666-6666-4666-8666-666666666666",
      amount_minor: 2_500_000,
      currency: "UZS",
      status: "SUCCESS",
      failure_reason: null,
      fraud_decision: "ALLOW",
      refunded_amount_minor: 0,
      description: "+998901234567",
      service_code: "beeline",
      service_account: "+998901234567",
      created_at: "2026-10-08T10:00:00Z",
      updated_at: "2026-10-08T10:00:00Z",
      completed_at: "2026-10-08T10:00:00Z",
      ...overrides,
    },
    201,
  );
}

const base = () => ({
  ...signedInRoutes(),
  "GET /api/v1/services": () => json(SERVICES),
  "GET /api/v1/wallets": () => json([USD, WALLET]),
  "GET /api/v1/transactions": () => json([]),
});

describe("service accounts", () => {
  it("accepts what each kind of provider identifies a customer by", () => {
    expect(isValidAccount("PHONE", "+998 90 123-45-67")).toBe(true);
    expect(isValidAccount("PHONE", "901234567")).toBe(true);
    expect(isValidAccount("PHONE", "+7 912 345 67 89")).toBe(false);
    expect(isValidAccount("PHONE", "90123")).toBe(false);
    expect(isValidAccount("ACCOUNT_NUMBER", "0012 3456-78")).toBe(true);
    expect(isValidAccount("ACCOUNT_NUMBER", "12345")).toBe(false);
    expect(isValidAccount("ACCOUNT_NUMBER", "12345a7")).toBe(false);
    expect(isValidAccount("LOGIN", "aziza_k-01")).toBe(true);
    expect(isValidAccount("LOGIN", "ab")).toBe(false);
    expect(isValidAccount("LOGIN", "has space")).toBe(false);
  });
});

describe("paying for services", () => {
  it("lists the providers by category and says the payments are a demo", async () => {
    fakeApi(base());
    renderApp("/pay");

    const mobile = (await screen.findByRole("heading", { name: "Mobile" })).closest("section")!;
    expect(within(mobile).getByRole("button", { name: /Beeline/ })).toBeInTheDocument();
    const utilities = screen.getByRole("heading", { name: "Utilities" }).closest("section")!;
    expect(within(utilities).getByRole("button", { name: /Electricity/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Television" })).toBeNull(); // nothing in it
    expect(screen.getByText(/not connected to these providers yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pay a merchant/ })).toHaveAttribute(
      "href",
      "/pay/merchant",
    );
  });

  it("pays a mobile number from the UZS card", async () => {
    const { requests } = fakeApi({
      ...base(),
      "POST /api/v1/services/beeline/payments": () => paid(),
    });
    renderApp("/pay");

    await userEvent.click(await screen.findByRole("button", { name: /Beeline/ }));
    // Only the card in the provider's currency is offered.
    expect(within(await screen.findByLabelText("From")).getAllByRole("option")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText(/Phone number/), "90 123 45 67");
    await userEvent.type(screen.getByLabelText(/Amount/), "25000");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));

    expect(await screen.findByText("Beeline · +998901234567")).toBeInTheDocument();
    expect(screen.getByText(/PAY-SVC/)).toBeInTheDocument();
    const sent = requests.find((r) => r.method === "POST" && r.path.startsWith("/api/v1/services"));
    expect(sent?.body).toEqual({
      source_wallet_id: WALLET.id,
      account: "90 123 45 67",
      amount: "25000",
    });
    expect(sent?.headers["idempotency-key"]).toBeTruthy();

    // Paying the same bill again keeps the account but not the amount.
    await userEvent.click(screen.getByRole("button", { name: "Pay Beeline again" }));
    expect(screen.getByLabelText(/Phone number/)).toHaveValue("90 123 45 67");
    expect(screen.getByLabelText(/Amount/)).toHaveValue("");
  });

  it("checks the account and the amount before calling the API", async () => {
    const { requests } = fakeApi({
      ...base(),
      [`GET /api/v1/limits/${WALLET.id}`]: () =>
        json({ ...noLimit(WALLET.id), daily_limit_minor: 5_000_000, remaining_minor: 2_000_000 }),
    });
    renderApp("/pay?service=electricity");

    const account = await screen.findByLabelText(/Account number/);
    const amount = screen.getByLabelText(/Amount/);
    const pay = screen.getByRole("button", { name: "Pay" });
    expect(screen.getByText("From 1,000.00 UZS to 5,000,000.00 UZS at a time.")).toBeInTheDocument();

    await userEvent.type(account, "12345");
    await userEvent.type(amount, "999");
    await userEvent.click(pay);
    expect(screen.getByText("An account number has 6 to 14 digits.")).toBeInTheDocument();
    expect(
      screen.getByText("Enter an amount from 1,000.00 UZS to 5,000,000.00 UZS."),
    ).toBeInTheDocument();

    await userEvent.type(account, "67");
    await userEvent.clear(amount);
    await userEvent.type(amount, "20000.01");
    await userEvent.click(pay);
    expect(screen.queryByText("An account number has 6 to 14 digits.")).toBeNull();
    expect(screen.getByText(/over your daily limit for this card/)).toBeInTheDocument();
    expect(requests.some((r) => r.path.startsWith("/api/v1/services/"))).toBe(false);
  });

  it("shows why a payment failed, in the reader's language", async () => {
    fakeApi({
      ...base(),
      "POST /api/v1/services/uzonline/payments": () =>
        paid({ status: "FAILED", failure_reason: "Insufficient Funds", service_account: "aziza01" }),
    });
    setLang("uz");
    renderApp("/pay?service=uzonline");

    await userEvent.type(await screen.findByLabelText(/Login/), "aziza01");
    await userEvent.type(screen.getByLabelText(/Summa/), "50000");
    await userEvent.click(screen.getByRole("button", { name: "To‘lash" }));

    expect(await screen.findByText(/Mablag‘ yetarli emas/)).toBeInTheDocument();
    expect(screen.getByText("Uzonline · aziza01")).toBeInTheDocument();
  });

  it("says so when the customer has no card in the provider's currency", async () => {
    fakeApi({ ...base(), "GET /api/v1/wallets": () => json([USD]) });
    renderApp("/pay?service=beeline");

    expect(await screen.findByText(/you have no UZS card yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pay" })).toBeNull();
  });

  it("shows the server's refusal and keeps what was typed", async () => {
    fakeApi({
      ...base(),
      "POST /api/v1/services/beeline/payments": () =>
        problem(422, "Invalid Service Account", "enter a phone number like +998 90 123 45 67"),
    });
    renderApp("/pay?service=beeline");

    await userEvent.type(await screen.findByLabelText(/Phone number/), "901234567");
    await userEvent.type(screen.getByLabelText(/Amount/), "5000");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));

    expect(await screen.findByText(/Invalid Service Account/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Phone number/)).toHaveValue("901234567");
  });

  it("an unknown service in the link is said to be unknown", async () => {
    fakeApi(base());
    renderApp("/pay?service=nope");

    expect(await screen.findByText("There is no such service.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← All services" })).toHaveAttribute("href", "/pay");
  });

  it("still pays a merchant by its id, on its own page", async () => {
    fakeApi(base());
    renderApp("/pay?merchant=3f2b8c1e-0000-4000-8000-000000000001");

    expect(await screen.findByRole("heading", { name: "Pay a merchant" })).toBeInTheDocument();
    expect(screen.getByLabelText("Merchant id")).toHaveValue("3f2b8c1e-0000-4000-8000-000000000001");
  });
});

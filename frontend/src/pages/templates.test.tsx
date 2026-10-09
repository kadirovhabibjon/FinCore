import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { minorToInput } from "../lib/money";
import { templateLink } from "../lib/templates";
import { WALLET, fakeApi, json, noContent, renderApp, signedInRoutes } from "../test/fakeApi";

const CARD = "9955123456789011";
const service = {
  id: "aaaaaaaa-0000-4000-8000-000000000001",
  kind: "SERVICE" as const,
  name: "My phone",
  service_code: "beeline",
  service_account: "+998901234567",
  card_number: null,
  recipient_name: null,
  currency: "UZS",
  amount_minor: 5_000_000 as number | null,
  created_at: "2026-10-09T10:00:00Z",
};
const transfer = {
  ...service,
  id: "aaaaaaaa-0000-4000-8000-000000000002",
  kind: "TRANSFER" as const,
  name: "Rent",
  service_code: null,
  service_account: null,
  card_number: CARD,
  recipient_name: "Bobur T.",
  amount_minor: null,
};
const SERVICES = [
  {
    code: "beeline",
    category: "MOBILE",
    name: "Beeline",
    account_kind: "PHONE",
    currency: "UZS",
    min_amount_minor: 100_000,
    max_amount_minor: 500_000_000,
  },
];
const paid = {
  id: "55555555-5555-4555-8555-555555555555",
  reference: "PAY-SVC",
  source_wallet_id: WALLET.id,
  merchant_id: "66666666-6666-4666-8666-666666666666",
  amount_minor: 2_500_000,
  currency: "UZS",
  status: "SUCCESS",
  failure_reason: null as string | null,
  fraud_decision: "ALLOW",
  refunded_amount_minor: 0,
  description: "+998901234567",
  service_code: "beeline",
  service_account: "+998901234567",
  created_at: "2026-10-09T10:00:00Z",
  updated_at: "2026-10-09T10:00:00Z",
  completed_at: "2026-10-09T10:00:00Z",
};
const base = () => ({
  ...signedInRoutes(),
  "GET /api/v1/wallets": () => json([WALLET]),
  "GET /api/v1/services": () => json(SERVICES),
});

describe("template links", () => {
  it("lead to the form the template fills in, amount included when it has one", () => {
    expect(minorToInput(5_000_000, "UZS")).toBe("50000.00");
    expect(templateLink(service)).toBe(
      "/pay?service=beeline&account=%2B998901234567&amount=50000.00",
    );
    expect(templateLink(transfer)).toBe(`/transfer?to=${CARD}`);
  });
});

describe("the home page", () => {
  it("offers quick actions, saved payments and the latest operations", async () => {
    fakeApi({
      ...base(),
      "GET /api/v1/templates": () => json([service, transfer]),
      "GET /api/v1/transactions": () =>
        json([
          {
            id: "77777777-7777-4777-8777-777777777771",
            type: "TRANSFER",
            direction: "IN",
            counterparty_name: "Aziza K.",
            reference: "TRF-IN",
            status: "COMPLETED",
            amount_minor: 7_500,
            currency: "UZS",
            description: null,
            created_at: "2026-10-09T09:00:00Z",
            completed_at: "2026-10-09T09:00:00Z",
          },
          {
            id: "77777777-7777-4777-8777-777777777772",
            type: "PAYMENT",
            direction: "OUT",
            counterparty_name: null,
            reference: "PAY-OUT",
            status: "FAILED",
            amount_minor: 100_000,
            currency: "UZS",
            description: "+998901234567",
            created_at: "2026-10-09T08:00:00Z",
            completed_at: null,
          },
        ]),
    });
    renderApp("/");

    const quick = await screen.findByRole("navigation", { name: "Quick actions" });
    expect(within(quick).getByRole("link", { name: "Send" })).toHaveAttribute("href", "/transfer");
    expect(within(quick).getByRole("link", { name: "Pay" })).toHaveAttribute("href", "/pay");
    expect(within(quick).getByRole("link", { name: "Request" })).toHaveAttribute("href", "/requests");
    // One wallet: nothing to exchange between.
    expect(within(quick).queryByRole("link", { name: "Exchange" })).toBeNull();

    const phone = await screen.findByRole("link", { name: /My phone/ });
    expect(phone).toHaveAttribute("href", templateLink(service));
    expect(phone).toHaveTextContent("Beeline · +998901234567 · 50,000.00 UZS");
    expect(screen.getByRole("link", { name: /Rent/ })).toHaveTextContent(
      "Transfer · Bobur T. ···· 9011 · amount typed each time",
    );
    expect(screen.getByRole("link", { name: "All templates" })).toHaveAttribute("href", "/templates");

    const received = await screen.findByRole("link", { name: /Aziza K\./ });
    expect(received).toHaveAttribute("href", "/transactions/77777777-7777-4777-8777-777777777771");
    expect(received).toHaveTextContent("+75.00 UZS");
    // The template names the same number; this is the operation's own row.
    const failed = screen
      .getAllByRole("link", { name: /\+998901234567/ })
      .find((link) => link.getAttribute("href")?.startsWith("/transactions/")) as HTMLElement;
    expect(failed).toHaveTextContent("1,000.00 UZS"); // no sign: nothing moved
    expect(within(failed).getByText("FAILED")).toBeInTheDocument();
  });

  it("stays the wallets page when there is nothing else to show", async () => {
    fakeApi(base());
    renderApp("/");

    expect(await screen.findByText("9955 0000 0000 0006")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Templates" })).toBeNull();
    expect(await screen.findByText(/Nothing yet. What you send, pay and receive/)).toBeInTheDocument();
  });
});

describe("saving and using a template", () => {
  it("saves a service payment after it is made, amount and all", async () => {
    const { requests } = fakeApi({
      ...base(),
      "POST /api/v1/services/beeline/payments": () => json(paid, 201),
      "POST /api/v1/templates": () => json(service, 201),
    });
    renderApp("/pay?service=beeline");

    await userEvent.type(await screen.findByLabelText(/Phone number/), "901234567");
    await userEvent.type(screen.getByLabelText(/Amount/), "25000");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save as template" }));

    const name = screen.getByLabelText("Template name");
    expect(name).toHaveValue("Beeline");
    expect(screen.getByLabelText("Remember the amount (25,000.00 UZS)")).toBeChecked();
    await userEvent.clear(name);
    await userEvent.type(name, "My phone");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Saved to your templates.")).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST" && r.path === "/api/v1/templates")?.body).toEqual({
      kind: "SERVICE",
      service_code: "beeline",
      account: "+998901234567",
      name: "My phone",
      amount: "25000.00",
    });
  });

  it("can leave the amount out, and is not offered for a payment that failed", async () => {
    let result = paid;
    const { requests } = fakeApi({
      ...base(),
      "POST /api/v1/services/beeline/payments": () => json(result, 201),
      "POST /api/v1/templates": () => json({ ...service, amount_minor: null }, 201),
    });
    renderApp("/pay?service=beeline");

    await userEvent.type(await screen.findByLabelText(/Phone number/), "901234567");
    await userEvent.type(screen.getByLabelText(/Amount/), "25000");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save as template" }));
    await userEvent.click(screen.getByLabelText(/Remember the amount/));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(
        (requests.find((r) => r.path === "/api/v1/templates" && r.method === "POST")?.body as {
          amount: string | null;
        }).amount,
      ).toBeNull(),
    );

    result = { ...paid, status: "FAILED", failure_reason: "Insufficient Funds" };
    await userEvent.click(screen.getByRole("button", { name: "Pay Beeline again" }));
    await userEvent.type(screen.getByLabelText(/Amount/), "25000");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    expect(await screen.findByText(/Insufficient Funds/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save as template" })).toBeNull();
  });

  it("opens the service form filled in, and pays only when the button is pressed", async () => {
    const { requests } = fakeApi({
      ...base(),
      "POST /api/v1/services/beeline/payments": () => json(paid, 201),
    });
    renderApp(templateLink(service));

    expect(await screen.findByLabelText(/Phone number/)).toHaveValue("+998901234567");
    expect(screen.getByLabelText(/Amount/)).toHaveValue("50000.00");
    expect(requests.some((r) => r.method === "POST" && r.path.startsWith("/api/v1/services"))).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    await waitFor(() =>
      expect(
        requests.find((r) => r.method === "POST" && r.path.startsWith("/api/v1/services"))?.body,
      ).toEqual({ source_wallet_id: WALLET.id, account: "+998901234567", amount: "50000.00" }),
    );
  });

  it("opens the send form with the card looked up and the amount filled in", async () => {
    fakeApi({
      ...base(),
      "GET /api/v1/transfers/recipient": () =>
        json({
          wallet_id: "33333333-3333-4333-8333-333333333333",
          currency: "UZS",
          display_name: "Bobur T.",
          own: false,
          card_last4: "9011",
        }),
    });
    renderApp(templateLink({ ...transfer, amount_minor: 120_000 }));

    expect(await screen.findByText("Bobur T.")).toBeInTheDocument();
    expect(screen.getByLabelText("To card number")).toHaveValue("9955 1234 5678 9011");
    expect(screen.getByLabelText(/Amount/)).toHaveValue("1200.00");
  });
});

describe("the templates page", () => {
  it("lists every template and deletes one on the second press", async () => {
    let saved = [service, transfer];
    const { requests } = fakeApi({
      ...base(),
      "GET /api/v1/templates": () => json(saved),
      [`DELETE /api/v1/templates/${transfer.id}`]: () => {
        saved = [service];
        return noContent();
      },
    });
    renderApp("/templates");

    const rent = (await screen.findByText("Rent")).closest("li") as HTMLElement;
    expect(within(rent).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      `/transfer?to=${CARD}`,
    );
    await userEvent.click(within(rent).getByRole("button", { name: "Delete" }));
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
    await userEvent.click(within(rent).getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(screen.queryByText("Rent")).toBeNull());
    expect(screen.getByText("My phone")).toBeInTheDocument();
  });

  it("says how to make one when there are none", async () => {
    fakeApi(base());
    renderApp("/templates");

    expect(await screen.findByText(/No templates yet/)).toBeInTheDocument();
  });
});

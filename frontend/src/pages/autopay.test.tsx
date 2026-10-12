import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../i18n";
import { WALLET, fakeApi, json, noContent, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const CARD = "9955123456789011";
const phoneTemplate = {
  id: "aaaaaaaa-0000-4000-8000-000000000001",
  kind: "SERVICE",
  name: "My phone",
  service_code: "beeline",
  service_account: "+998901234567",
  card_number: null,
  recipient_name: null,
  currency: "UZS",
  amount_minor: 5_000_000,
  created_at: "2026-10-09T10:00:00Z",
};
const rentTemplate = {
  ...phoneTemplate,
  id: "aaaaaaaa-0000-4000-8000-000000000002",
  kind: "TRANSFER",
  name: "Rent",
  service_code: null,
  service_account: null,
  card_number: CARD,
  recipient_name: "Bobur T.",
  amount_minor: null,
};
const scheduled = (overrides: Record<string, unknown> = {}) => ({
  id: "bbbbbbbb-0000-4000-8000-000000000001",
  name: "My phone",
  kind: "SERVICE",
  service_code: "beeline",
  service_account: "+998901234567",
  card_number: null,
  recipient_name: null,
  source_wallet_id: WALLET.id,
  currency: "UZS",
  amount_minor: 5_000_000,
  interval: "MONTHLY",
  day: 5,
  status: "ACTIVE",
  next_run_at: "2026-11-05T04:00:00Z",
  last_run_at: null,
  last_status: null,
  last_error: null,
  last_operation_id: null,
  created_at: "2026-10-12T10:00:00Z",
  ...overrides,
});
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
const USD = { ...WALLET, id: "99999999-0000-4000-8000-000000000009", currency: "USD" };

function page(list: unknown[], extra: Parameters<typeof fakeApi>[0] = {}) {
  let items = list;
  return fakeApi({
    ...signedInRoutes(),
    "GET /api/v1/wallets": () => json([USD, WALLET]),
    "GET /api/v1/services": () => json(SERVICES),
    "GET /api/v1/templates": () => json([phoneTemplate, rentTemplate]),
    "GET /api/v1/scheduled-payments": () => json(items),
    "POST /api/v1/scheduled-payments": () => {
      items = [...items, scheduled()];
      return json(scheduled(), 201);
    },
    ...extra,
  });
}

describe("scheduled payments", () => {
  it("says what each one pays, when, and how the last run went", async () => {
    page([
      scheduled({
        last_run_at: "2026-10-05T04:00:00Z",
        last_status: "FAILED",
        last_error: "Insufficient Funds",
        last_operation_id: "77777777-7777-4777-8777-777777777777",
      }),
      scheduled({
        id: "bbbbbbbb-0000-4000-8000-000000000002",
        name: "Rent",
        kind: "TRANSFER",
        service_code: null,
        service_account: null,
        card_number: CARD,
        recipient_name: "Bobur T.",
        amount_minor: 250_000,
        interval: "WEEKLY",
        day: 1,
        status: "PAUSED",
      }),
    ]);
    renderApp("/autopay");

    const phone = (await screen.findByText("Beeline · +998901234567 · 50,000.00 UZS")).closest(
      "li",
    ) as HTMLElement;
    expect(phone).toHaveTextContent("Every month on day 5");
    expect(phone).toHaveTextContent("Next: Nov 5, 2026");
    expect(within(phone).getByText("FAILED")).toBeInTheDocument();
    expect(phone).toHaveTextContent("Insufficient Funds");
    expect(within(phone).getByRole("link", { name: "see the operation" })).toHaveAttribute(
      "href",
      "/transactions/77777777-7777-4777-8777-777777777777",
    );

    const rent = screen
      .getByText("Transfer · Bobur T. ···· 9011 · 2,500.00 UZS")
      .closest("li") as HTMLElement;
    expect(rent).toHaveTextContent("Every Monday");
    expect(rent).toHaveTextContent("Paused");
    expect(rent).toHaveTextContent("Not run yet");
    expect(within(rent).getByRole("button", { name: "Resume" })).toBeInTheDocument();
  });

  it("schedules a template: its amount, a card in its currency, a day", async () => {
    const { requests } = page([]);
    renderApp(`/autopay?template=${phoneTemplate.id}`);

    expect(await screen.findByText("No scheduled payments yet.")).toBeInTheDocument();
    expect(await screen.findByLabelText("Amount each time (UZS)")).toHaveValue("50000.00");
    // Only the card in the template's currency can pay it.
    expect(within(screen.getByLabelText("From card")).getAllByRole("option")).toHaveLength(1);

    await userEvent.selectOptions(screen.getByLabelText("How often"), "Every week");
    await userEvent.selectOptions(screen.getByLabelText("Day of the week"), "Friday");
    await userEvent.click(screen.getByRole("button", { name: "Schedule it" }));

    await waitFor(() =>
      expect(
        requests.find((r) => r.method === "POST" && r.path === "/api/v1/scheduled-payments")?.body,
      ).toEqual({
        name: "My phone",
        kind: "SERVICE",
        service_code: "beeline",
        account: "+998901234567",
        card_number: null,
        source_wallet_id: WALLET.id,
        amount: "50000.00",
        interval: "WEEKLY",
        day: 5,
      }),
    );
    // The new one is listed (it shares its line with when it runs next).
    expect(await screen.findByText(/Every month on day 5/)).toBeInTheDocument();
  });

  it("asks for the amount a template doesn't carry, and checks it", async () => {
    const { requests } = page([]);
    renderApp("/autopay");

    await userEvent.selectOptions(await screen.findByLabelText("What to pay"), rentTemplate.id);
    const amount = screen.getByLabelText("Amount each time (UZS)");
    expect(amount).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Schedule it" }));
    expect(await screen.findByText(/at most 2 decimals/)).toBeInTheDocument();
    expect(requests.some((r) => r.method === "POST" && r.path.endsWith("scheduled-payments"))).toBe(
      false,
    );

    await userEvent.type(amount, "2500");
    await userEvent.selectOptions(screen.getByLabelText("Day of the month"), "28");
    await userEvent.click(screen.getByRole("button", { name: "Schedule it" }));
    await waitFor(() =>
      expect(
        requests.find((r) => r.method === "POST" && r.path.endsWith("scheduled-payments"))?.body,
      ).toMatchObject({ kind: "TRANSFER", card_number: CARD, amount: "2500", day: 28 }),
    );
  });

  it("pauses, resumes and deletes", async () => {
    let item = scheduled();
    let gone = false;
    const url = `/api/v1/scheduled-payments/${item.id}`;
    const { requests } = page([], {
      "GET /api/v1/scheduled-payments": () => json(gone ? [] : [item]),
      [`PATCH ${url}`]: (request) => {
        item = { ...item, status: (request.body as { status: string }).status };
        return json(item);
      },
      [`DELETE ${url}`]: () => {
        gone = true;
        return noContent();
      },
    });
    renderApp("/autopay");

    await userEvent.click(await screen.findByRole("button", { name: "Pause" }));
    expect(await screen.findByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ status: "PAUSED" });

    await userEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(requests.some((r) => r.method === "DELETE")).toBe(false); // armed, not done
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText("No scheduled payments yet.")).toBeInTheDocument();
  });

  it("says why a run could not be made, in the reader's language", async () => {
    setLang("uz");
    page([
      scheduled({
        last_run_at: "2026-10-05T04:00:00Z",
        last_status: "NOT_RUN",
        last_error: "Recipient Not Found",
      }),
    ]);
    renderApp("/autopay");

    const row = (await screen.findByText("Har oyning 5-kuni", { exact: false })).closest(
      "li",
    ) as HTMLElement;
    expect(within(row).getByText("Bajarilmadi")).toBeInTheDocument();
    expect(row).toHaveTextContent("Qabul qiluvchi topilmadi");
  });

  it("explains that one is made from a template when there are none", async () => {
    page([], { "GET /api/v1/templates": () => json([]) });
    renderApp("/autopay");

    expect(await screen.findByText(/A scheduled payment is made from a template/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Schedule it" })).toBeNull();
  });

  it("shows the server's refusal", async () => {
    page([], {
      "POST /api/v1/scheduled-payments": () =>
        problem(409, "Too Many Scheduled Payments", "at most 20; delete one first"),
    });
    renderApp("/autopay");

    await userEvent.click(await screen.findByRole("button", { name: "Schedule it" }));
    expect(await screen.findByText(/Too Many Scheduled Payments/)).toBeInTheDocument();
  });
});

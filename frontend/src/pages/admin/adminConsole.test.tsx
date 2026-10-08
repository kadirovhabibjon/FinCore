import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../../i18n";
import { USER, fakeApi, json, problem, renderApp, signedInRoutes } from "../../test/fakeApi";

const ADMIN = { ...USER, roles: ["USER", "ADMIN"] };
const CUSTOMER = {
  ...USER,
  id: "77777777-7777-4777-8777-777777777777",
  first_name: "Aziza",
  last_name: "Karimova",
  email: "aziza@example.com",
  phone: "+998901112244",
};
const review = (id: string) => ({
  id,
  type: "TRANSFER",
  reference: `TRF-${id.slice(0, 4)}`,
  initiator_user_id: CUSTOMER.id,
  counterparty_id: "33333333-3333-4333-8333-333333333333",
  amount_minor: 900_000_00,
  currency: "UZS",
  status: "PENDING",
  failure_reason: null,
  fraud_decision: "REVIEW",
  reviewed_by_user_id: null,
  reviewed_at: null,
  created_at: "2026-10-08T10:00:00Z",
});
const thread = (userId: string, overrides: Record<string, unknown> = {}) => ({
  user_id: userId,
  status: "OPEN",
  last_message_at: "2026-10-08T10:00:00Z",
  last_sender: "CUSTOMER",
  last_body: "Hello",
  unread_count: 0,
  ...overrides,
});

describe("the admin menu", () => {
  it("counts what is waiting: reviews to decide and messages nobody opened", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () =>
        json([review("aaaa1111-0000-4000-8000-000000000001"), review("bbbb2222-0000-4000-8000-000000000002")]),
      "GET /api/v1/admin/support/threads": () =>
        json({ waiting_count: 1, unread_count: 3, items: [thread(CUSTOMER.id, { unread_count: 3 })] }),
      "GET /api/v1/admin/users": () => json([]),
    });
    renderApp("/admin/users");

    const menu = await screen.findByRole("navigation", { name: "Admin" });
    const reviews = within(menu).getByRole("link", { name: /Fraud reviews/ });
    const support = within(menu).getByRole("link", { name: /Support/ });
    expect(await within(reviews).findByLabelText("2 waiting for a decision")).toHaveTextContent("2");
    expect(await within(support).findByLabelText("3 unread")).toHaveTextContent("3");
    // Nothing waiting, nothing shown - not a zero.
    for (const name of [/Users/, /Transactions/, /Webhooks/, /Announcements/]) {
      expect(within(menu).getByRole("link", { name }).querySelector(".admin-count")).toBeNull();
    }
  });

  it("shows no counts when nothing is waiting", async () => {
    fakeApi({ ...signedInRoutes(ADMIN), "GET /api/v1/admin/users": () => json([]) });
    renderApp("/admin/users");

    const menu = await screen.findByRole("navigation", { name: "Admin" });
    await screen.findByText("No users match.");
    expect(menu.querySelector(".admin-count")).toBeNull();
  });
});

describe("admin tables", () => {
  it("name the customer instead of showing an id, linked to their page", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () => json([review("aaaa1111-0000-4000-8000-000000000001")]),
      [`GET /api/v1/admin/users/${CUSTOMER.id}`]: () => json(CUSTOMER),
    });
    renderApp("/admin/reviews");

    const name = await screen.findByRole("link", { name: "Aziza Karimova" });
    expect(name).toHaveAttribute("href", `/admin/users/${CUSTOMER.id}`);
  });

  it("fall back to the start of the id when the customer can't be looked up", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () => json([review("aaaa1111-0000-4000-8000-000000000001")]),
    });
    renderApp("/admin/reviews");

    expect(await screen.findByRole("link", { name: "77777777" })).toBeInTheDocument();
  });
});

describe("the users page", () => {
  const routes = (requests: { status?: string } = {}) => ({
    ...signedInRoutes(ADMIN),
    "GET /api/v1/admin/users": () => json([{ ...CUSTOMER, status: requests.status ?? "ACTIVE" }]),
    [`POST /api/v1/admin/users/${CUSTOMER.id}/status`]: (request: { body?: unknown }) => {
      requests.status = (request.body as { status: string }).status;
      return json({ ...CUSTOMER, status: requests.status });
    },
  });

  it("takes its search from the link, and puts a new search in it", async () => {
    const { requests } = fakeApi(routes());
    renderApp(`/admin/users?q=${CUSTOMER.id}`);

    expect(await screen.findByLabelText("Search users")).toHaveValue(CUSTOMER.id);
    await screen.findByText("aziza@example.com");
    const first = requests.find((r) => r.path === "/api/v1/admin/users");
    expect(new URLSearchParams(first!.search).get("q")).toBe(CUSTOMER.id);
    expect(screen.getByRole("link", { name: "messages" })).toHaveAttribute(
      "href",
      `/admin/support?user=${CUSTOMER.id}`,
    );

    await userEvent.clear(screen.getByLabelText("Search users"));
    await userEvent.type(screen.getByLabelText("Search users"), "aziza");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(
        requests.some(
          (r) => r.path === "/api/v1/admin/users" && new URLSearchParams(r.search).get("q") === "aziza",
        ),
      ).toBe(true),
    );
  });

  it("asks before taking someone's access away, and can be called off", async () => {
    const { requests } = fakeApi(routes());
    renderApp("/admin/users");
    const changed = () => requests.some((r) => r.method === "POST" && r.path.endsWith("/status"));

    const status = await screen.findByLabelText("Status of aziza@example.com");
    await userEvent.selectOptions(status, "BLOCKED");
    const dialog = screen.getByRole("alertdialog", { name: "Confirm" });
    expect(dialog).toHaveTextContent("Set aziza@example.com to BLOCKED?");
    expect(dialog).toHaveTextContent("signed out everywhere");
    expect(changed()).toBe(false);

    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(status).toHaveValue("ACTIVE");
    expect(changed()).toBe(false);

    await userEvent.selectOptions(status, "BLOCKED");
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Confirm" }),
    );
    await waitFor(() => expect(changed()).toBe(true));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(await screen.findByLabelText("Status of aziza@example.com")).toHaveValue("BLOCKED");
  });
});

describe("armed buttons", () => {
  it("rejecting a review takes a second press, and looking away disarms it", async () => {
    const id = "aaaa1111-0000-4000-8000-000000000001";
    const { requests } = fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () => json([review(id)]),
      [`POST /api/v1/admin/reviews/${id}`]: () => json({ ...review(id), status: "FAILED" }),
    });
    renderApp("/admin/reviews");
    const decided = () => requests.find((r) => r.method === "POST" && r.path.includes("/reviews/"));

    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    expect(screen.getByRole("button", { name: "Confirm reject" })).toBeInTheDocument();
    await userEvent.tab(); // focus moves on: back to a plain "Reject"
    expect(screen.queryByRole("button", { name: "Confirm reject" })).toBeNull();
    expect(decided()).toBeUndefined();

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    await waitFor(() => expect(decided()?.body).toEqual({ decision: "REJECT" }));
  });
});

describe("the support inbox", () => {
  it("lists open conversations, and resolved ones only when asked", async () => {
    const open = thread(CUSTOMER.id, { last_body: "Still waiting" });
    const done = thread("88888888-8888-4888-8888-888888888888", {
      status: "RESOLVED",
      last_sender: "STAFF",
      last_body: "Glad it worked.",
    });
    const { requests } = fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/support/threads": (request) =>
        json({
          waiting_count: 1,
          unread_count: 0,
          items: new URLSearchParams(request.search).get("status") === "OPEN" ? [open] : [open, done],
        }),
    });
    renderApp("/admin/support");

    expect(await screen.findByText("Still waiting")).toBeInTheDocument();
    expect(screen.queryByText(/Glad it worked/)).toBeNull();

    await userEvent.click(screen.getByLabelText("Show resolved"));
    expect(await screen.findByText(/Glad it worked/)).toBeInTheDocument();
    expect(
      requests.some(
        (r) => r.path === "/api/v1/admin/support/threads" && !new URLSearchParams(r.search).has("status"),
      ),
    ).toBe(true);
  });
});

describe("the dashboard", () => {
  const day = (date: string, values: Record<string, number> = {}) => ({
    date,
    transfers: 0,
    payments: 0,
    exchanges: 0,
    failed: 0,
    volume_minor: 0,
    ...values,
  });
  const routes = () => ({
    ...signedInRoutes(ADMIN),
    "GET /api/v1/admin/reviews": () => json([review("aaaa1111-0000-4000-8000-000000000001")]),
    "GET /api/v1/admin/support/threads": () =>
      json({ waiting_count: 4, unread_count: 0, items: [] }),
    "GET /api/v1/admin/stats": () =>
      json({
        generated_at: "2026-10-08T10:00:00Z",
        awaiting_review: 1,
        currencies: [
          { currency: "USD", days: [day("2026-10-07"), day("2026-10-08", { exchanges: 2 })] },
          {
            currency: "UZS",
            days: [
              day("2026-10-07", { transfers: 3, volume_minor: 300_000 }),
              day("2026-10-08", { transfers: 5, payments: 2, failed: 1, volume_minor: 1_250_000 }),
            ],
          },
        ],
      }),
    "GET /api/v1/admin/users/stats": () =>
      json({
        total: 120,
        by_status: { ACTIVE: 117, BLOCKED: 2, SUSPENDED: 1 },
        days: [
          { date: "2026-10-07", registered: 4 },
          { date: "2026-10-08", registered: 6 },
        ],
      }),
  });
  // A tile by its label (the same words also head a column of the table).
  const tile = (label: string) =>
    screen
      .getAllByText(label)
      .map((element) => element.closest(".stat"))
      .find(Boolean) as HTMLElement;

  it("says what is waiting and what happened today, one currency at a time", async () => {
    fakeApi(routes());
    renderApp("/admin");

    // Opens on the currency most of the activity is in.
    expect(await screen.findByRole("heading", { name: "Today, UZS" })).toBeInTheDocument();
    expect(within(tile("Customers")).getByText("120")).toBeInTheDocument();
    expect(tile("Customers")).toHaveTextContent("6 new today · 3 blocked or suspended");
    expect(within(tile("Waiting for review")).getByText("1")).toBeInTheDocument();
    expect(within(tile("Waiting for an answer")).getByText("4")).toBeInTheDocument();
    expect(within(tile("Operations")).getByText("7")).toBeInTheDocument();
    expect(within(tile("Money moved")).getByText("12,500.00 UZS")).toBeInTheDocument();
    expect(within(tile("Failed")).getByText("1")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Currency"), "USD");
    expect(await screen.findByRole("heading", { name: "Today, USD" })).toBeInTheDocument();
    expect(tile("Operations")).toHaveTextContent("0 transfers · 0 payments · 2 exchanges");
  });

  it("draws each day, reads it out, and gives the same numbers as a table", async () => {
    fakeApi(routes());
    renderApp("/admin");

    const operations = await screen.findByRole("group", {
      name: "Operations started on each day in UZS",
    });
    expect(within(operations).getByRole("img", { name: "Oct 7: 3 operations" })).toBeInTheDocument();
    const today = within(operations).getByRole("img", { name: "Oct 8: 7 operations" });
    today.focus();
    const readout = await screen.findByRole("status");
    expect(readout).toHaveTextContent("5 transfers · 2 payments · 0 exchanges");
    expect(readout).toHaveTextContent("1 failed · 12,500.00 UZS moved");

    const users = screen.getByRole("group", { name: "Accounts created on each day" });
    expect(within(users).getByRole("img", { name: "Oct 8: 6 new customers" })).toBeInTheDocument();

    const table = within(operations.closest(".card") as HTMLElement).getByRole("table", {
      hidden: true,
    });
    expect(within(table).getAllByRole("row", { hidden: true })).toHaveLength(3);
    expect(table).toHaveTextContent("12,500.00 UZS");
  });

  it("asks for another period when one is chosen", async () => {
    const { requests } = fakeApi(routes());
    renderApp("/admin");

    await userEvent.selectOptions(await screen.findByLabelText("Period"), "30");
    await waitFor(() =>
      expect(
        requests.filter((r) => r.path.endsWith("/stats")).map((r) => new URLSearchParams(r.search).get("days")),
      ).toEqual(expect.arrayContaining(["14", "30"])),
    );
  });

  it("says so when nothing has happened yet", async () => {
    fakeApi(signedInRoutes(ADMIN));
    renderApp("/admin");

    expect(await screen.findByText("Nothing has happened in this period yet.")).toBeInTheDocument();
  });
});

describe("a customer's page", () => {
  const wallet = {
    id: "22222222-2222-4222-8222-222222222222",
    card_number: "9955000000000006",
    currency: "UZS",
    status: "ACTIVE",
    created_at: "2026-09-01T10:00:00Z",
    balance_minor: 150_000,
    held_minor: 25_000,
    name: "Salary",
    is_primary: true,
    blocked: true,
  };
  const operation = {
    ...review("cccc3333-0000-4000-8000-000000000003"),
    status: "FAILED",
    failure_reason: "Insufficient Funds",
    direction: "OUT",
    counterparty_name: "Bobur T.",
    description: null,
    completed_at: null,
    updated_at: "2026-10-08T10:00:00Z",
    source_wallet_id: wallet.id,
  };

  it("puts who they are, their wallets, operations and messages on one page", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      [`GET /api/v1/admin/users/${CUSTOMER.id}`]: () => json(CUSTOMER),
      "GET /api/v1/admin/wallets": () => json([wallet]),
      "GET /api/v1/admin/transactions": () => json([operation]),
      [`GET /api/v1/admin/support/threads/${CUSTOMER.id}`]: () =>
        json({ ...thread(CUSTOMER.id, { last_body: "Where is my money?" }), items: [] }),
    });
    renderApp(`/admin/users/${CUSTOMER.id}`);

    expect(await screen.findByRole("heading", { level: 1, name: "Aziza Karimova" })).toBeInTheDocument();
    expect(screen.getAllByText(/aziza@example.com/).length).toBeGreaterThan(0);

    expect(await screen.findByText("9955 0000 0000 0006")).toBeInTheDocument();
    expect(screen.getByText("Salary")).toBeInTheDocument();
    expect(screen.getByText("1,250.00 UZS")).toBeInTheDocument(); // available, not the ledger balance
    expect(screen.getByText("main · blocked by owner")).toBeInTheDocument();

    expect(await screen.findByText(operation.reference)).toBeInTheDocument();
    expect(screen.getByText(/→ Bobur T\./)).toBeInTheDocument();
    expect(screen.getByText("Insufficient Funds")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /All of this customer's operations/ })).toHaveAttribute(
      "href",
      `/admin/transactions?user_id=${CUSTOMER.id}`,
    );

    expect(await screen.findByText("Where is my money?")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open the conversation/ })).toHaveAttribute(
      "href",
      `/admin/support?user=${CUSTOMER.id}`,
    );
  });

  it("says what a customer doesn't have, rather than failing", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      [`GET /api/v1/admin/users/${CUSTOMER.id}`]: () => json(CUSTOMER),
      "GET /api/v1/admin/wallets": () => json([]),
      "GET /api/v1/admin/transactions": () => json([]),
      [`GET /api/v1/admin/support/threads/${CUSTOMER.id}`]: () =>
        problem(404, "Support Thread Not Found"),
    });
    renderApp(`/admin/users/${CUSTOMER.id}`);

    expect(await screen.findByText("This customer has no wallets.")).toBeInTheDocument();
    expect(await screen.findByText("This customer has not started any operation.")).toBeInTheDocument();
    expect(await screen.findByText("This customer has never written to support.")).toBeInTheDocument();
  });

  it("an unknown customer is said to be unknown", async () => {
    fakeApi(signedInRoutes(ADMIN));
    renderApp(`/admin/users/${CUSTOMER.id}`);

    expect(await screen.findByText(/User Not Found/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← All users" })).toHaveAttribute("href", "/admin/users");
  });
});

describe("the transactions page", () => {
  const exchange = {
    ...review("dddd4444-0000-4000-8000-000000000004"),
    type: "EXCHANGE",
    reference: "EXC-0001",
    status: "COMPLETED",
    direction: "SELF",
    amount_minor: 10_000,
    currency: "USD",
    received_amount_minor: 120_000_000,
    received_currency: "UZS",
    counterparty_name: null,
    fraud_decision: null,
    description: null,
    completed_at: "2026-10-08T10:00:00Z",
    updated_at: "2026-10-08T10:00:00Z",
    source_wallet_id: "22222222-2222-4222-8222-222222222222",
  };

  it("lists exchanges with what was received, and filters to them", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/transactions": () => json([exchange]),
    });
    renderApp("/admin/transactions");

    expect(await screen.findByText("EXC-0001")).toBeInTheDocument();
    expect(screen.getByText("100.00 USD")).toBeInTheDocument();
    expect(screen.getByText("for 1,200,000.00 UZS")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Type"), "Exchanges");
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.path === "/api/v1/admin/transactions" &&
            new URLSearchParams(r.search).get("type") === "EXCHANGE",
        ),
      ).toBe(true),
    );
  });

  it("downloads what is listed, under the same filters", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/transactions": () => json([exchange]),
      "GET /api/v1/admin/transactions/export.csv": () =>
        new Response("Date (UTC),Type\r\n", {
          status: 200,
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": 'attachment; filename="fincore-transactions-2026-10-08.csv"',
          },
        }),
    });
    URL.createObjectURL = () => "blob:test";
    URL.revokeObjectURL = () => undefined;
    renderApp(`/admin/transactions?status=FAILED&user_id=${CUSTOMER.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/export.csv"))).toBe(true));
    const sent = new URLSearchParams(requests.find((r) => r.path.endsWith("/export.csv"))!.search);
    expect(sent.get("status")).toBe("FAILED");
    expect(sent.get("user_id")).toBe(CUSTOMER.id);
    expect(sent.has("type")).toBe(false);
  });
});

describe("the console in another language", () => {
  it("is translated: menu, page and statuses", async () => {
    setLang("uz");
    fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () => json([review("aaaa1111-0000-4000-8000-000000000001")]),
    });
    renderApp("/admin/reviews");

    const menu = await screen.findByRole("navigation", { name: "Admin" });
    expect(within(menu).getByRole("link", { name: /Bosh sahifa/ })).toBeInTheDocument();
    expect(within(menu).getByRole("link", { name: /Murojaatlar/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Firibgarlik tekshiruvi navbati" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rad etish" })).toBeInTheDocument();
    expect(screen.getByText("O‘TKAZMA")).toBeInTheDocument();

    await userEvent.selectOptions(within(menu.parentElement!).getByLabelText("Til"), "ru");
    expect(await screen.findByRole("heading", { name: "Очередь проверки операций" })).toBeInTheDocument();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { USER, fakeApi, json, renderApp, signedInRoutes } from "../../test/fakeApi";

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
  it("name the customer instead of showing an id, linked to the Users page", async () => {
    fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/reviews": () => json([review("aaaa1111-0000-4000-8000-000000000001")]),
      [`GET /api/v1/admin/users/${CUSTOMER.id}`]: () => json(CUSTOMER),
    });
    renderApp("/admin/reviews");

    const name = await screen.findByRole("link", { name: "Aziza Karimova" });
    expect(name).toHaveAttribute("href", `/admin/users?q=${CUSTOMER.id}`);
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

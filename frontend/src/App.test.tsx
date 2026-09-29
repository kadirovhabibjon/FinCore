import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { USER, WALLET, fakeApi, json, noContent, problem, renderApp, signedInRoutes } from "./test/fakeApi";

describe("signing in", () => {
  it("sends a signed-out visitor to the login page", async () => {
    fakeApi({ "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") });

    renderApp("/transactions");

    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
  });

  it("restores the session from the refresh cookie on reload", async () => {
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]) });

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();
    // available = balance - held
    expect(await screen.findByText("1,250.00 UZS")).toBeInTheDocument();
  });

  it("logs in with the cookie transport and lands where the user was headed", async () => {
    const { requests } = fakeApi({
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/login": () =>
        json({ access_token: "access-1", refresh_token: null, expires_in: 900 }),
      "GET /api/v1/users/me": () => json(USER),
      "GET /api/v1/transactions": () => json([]),
    });
    renderApp("/transactions");

    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "History" })).toBeInTheDocument();
    const login = requests.find((r) => r.path === "/api/v1/auth/login");
    expect(login?.headers["x-refresh-token-transport"]).toBe("cookie");
    const me = requests.find((r) => r.path === "/api/v1/users/me");
    expect(me?.headers.authorization).toBe("Bearer access-1");
  });

  it("shows the API's reason when login fails", async () => {
    fakeApi({
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/login": () => problem(401, "Invalid Credentials"),
    });
    renderApp("/login");

    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid Credentials");
  });

  it("signing out clears the cookie server-side and returns to login", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "POST /api/v1/auth/logout": () => noContent(),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
    const logout = requests.find((r) => r.path === "/api/v1/auth/logout");
    expect(logout?.headers["x-refresh-token-transport"]).toBe("cookie");
  });
});

describe("roles", () => {
  it("hides the admin area from a plain user", async () => {
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([]) });

    renderApp("/admin/users");

    expect(await screen.findByRole("heading", { name: "Not allowed" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("lets SUPPORT look at the review queue but not decide", async () => {
    fakeApi({
      ...signedInRoutes({ ...USER, roles: ["SUPPORT", "USER"] }),
      "GET /api/v1/admin/reviews": () => json([reviewItem()]),
    });

    renderApp("/admin/reviews");

    expect(await screen.findByText("TRF-REVIEW01")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByText("ADMIN decides")).toBeInTheDocument();
  });

  it("lets ADMIN approve a review and shows where it landed", async () => {
    let queue = [reviewItem()];
    const { requests } = fakeApi({
      ...signedInRoutes({ ...USER, roles: ["ADMIN", "USER"] }),
      "GET /api/v1/admin/reviews": () => json(queue),
      [`POST /api/v1/admin/reviews/${reviewItem().id}`]: () => {
        queue = [];
        return json({ ...reviewItem(), status: "COMPLETED" });
      },
    });
    renderApp("/admin/reviews");

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    const notice = await screen.findByText(/is now/);
    expect(within(notice).getByText("COMPLETED")).toBeInTheDocument();
    expect(await screen.findByText("Nothing is waiting for review.")).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST" && r.path.includes("reviews"))?.body).toEqual({
      decision: "APPROVE",
    });
  });
});

describe("sending money", () => {
  const destination = "33333333-3333-4333-8333-333333333333";

  it("validates the amount before calling the API", async () => {
    const { requests } = fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]) });
    renderApp("/transfer");

    await userEvent.type(await screen.findByLabelText("To wallet id"), destination);
    await userEvent.type(screen.getByLabelText(/Amount/), "10.555");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/at most 2 decimals/)).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/transfers")).toBe(false);
  });

  it("retries with the same Idempotency-Key and sends the amount as a string", async () => {
    let attempts = 0;
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transactions": () => json([]),
      "POST /api/v1/transfers": (request) => {
        attempts += 1;
        if (attempts === 1) return problem(503, "Service Unavailable");
        const body = request.body as { amount: string };
        return json(
          {
            id: "44444444-4444-4444-8444-444444444444",
            reference: "TRF-ABC",
            source_wallet_id: WALLET.id,
            destination_wallet_id: destination,
            amount_minor: 1050,
            currency: "UZS",
            status: "PENDING",
            failure_reason: null,
            fraud_decision: "REVIEW",
            description: null,
            created_at: "2026-09-29T10:00:00Z",
            updated_at: "2026-09-29T10:00:00Z",
            completed_at: null,
            _echo: body.amount,
          },
          201,
        );
      },
    });
    renderApp(`/transfer?from=${WALLET.id}`);

    await userEvent.type(await screen.findByLabelText("To wallet id"), destination);
    await userEvent.type(screen.getByLabelText(/Amount/), "10.50");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Service Unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/waiting for a manual fraud review/)).toBeInTheDocument();
    const posts = requests.filter((r) => r.path === "/api/v1/transfers");
    expect(posts).toHaveLength(2);
    expect(posts[0]?.headers["idempotency-key"]).toBeTruthy();
    expect(posts[1]?.headers["idempotency-key"]).toBe(posts[0]?.headers["idempotency-key"]);
    expect(posts[0]?.body).toMatchObject({
      source_wallet_id: WALLET.id,
      destination_wallet_id: destination,
      amount: "10.50",
      currency: "UZS",
    });
  });

  it("uses a fresh Idempotency-Key for the next transfer", async () => {
    const created = {
      id: "55555555-5555-4555-8555-555555555555",
      reference: "TRF-DONE",
      source_wallet_id: WALLET.id,
      destination_wallet_id: destination,
      amount_minor: 100,
      currency: "UZS",
      status: "COMPLETED",
      failure_reason: null,
      fraud_decision: "ALLOW",
      description: null,
      created_at: "2026-09-29T10:00:00Z",
      updated_at: "2026-09-29T10:00:00Z",
      completed_at: "2026-09-29T10:00:01Z",
    };
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transactions": () => json([]),
      "POST /api/v1/transfers": () => json(created, 201),
    });
    renderApp("/transfer");

    for (let i = 0; i < 2; i += 1) {
      await userEvent.type(await screen.findByLabelText("To wallet id"), destination);
      await userEvent.type(screen.getByLabelText(/Amount/), "1");
      await userEvent.click(screen.getByRole("button", { name: "Send" }));
      await screen.findByText("The money has moved.");
      if (i === 0) await userEvent.click(screen.getByRole("button", { name: "Send another" }));
    }

    const keys = requests
      .filter((r) => r.path === "/api/v1/transfers")
      .map((r) => r.headers["idempotency-key"]);
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).not.toBe(keys[1]);
  });
});

describe("sessions", () => {
  it("lists sessions and signs out another device", async () => {
    const sessions = [
      {
        id: "s-current",
        created_at: "2026-09-29T09:00:00Z",
        last_used_at: "2026-09-29T09:30:00Z",
        user_agent: "Firefox",
        ip_address: "203.0.113.7",
        current: true,
      },
      {
        id: "s-phone",
        created_at: "2026-09-28T09:00:00Z",
        last_used_at: null,
        user_agent: "Pixel Browser",
        ip_address: "198.51.100.2",
        current: false,
      },
    ];
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/users/me/sessions": () => json(sessions),
      "DELETE /api/v1/users/me/sessions/s-phone": () => {
        sessions.pop();
        return noContent();
      },
    });
    renderApp("/settings");

    const phoneRow = (await screen.findByText("Pixel Browser")).closest("tr")!;
    expect(within(screen.getByText("Firefox").closest("tr")!).getByText("This device")).toBeVisible();
    await userEvent.click(within(phoneRow).getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(screen.queryByText("Pixel Browser")).not.toBeInTheDocument());
    expect(requests.some((r) => r.method === "DELETE")).toBe(true);
  });
});

function reviewItem() {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    type: "TRANSFER",
    reference: "TRF-REVIEW01",
    status: "PENDING",
    amount_minor: 5_000_000,
    currency: "UZS",
    description: null,
    created_at: "2026-09-29T08:00:00Z",
    completed_at: null,
    initiator_user_id: USER.id,
    source_wallet_id: WALLET.id,
    counterparty_id: "77777777-7777-4777-8777-777777777777",
    failure_reason: null,
    fraud_decision: "REVIEW",
    reviewed_by_user_id: null,
    reviewed_at: null,
    updated_at: "2026-09-29T08:00:00Z",
  };
}

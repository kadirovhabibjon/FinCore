import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { authTiming } from "./auth/tokenStore";

import { RATES, USER, WALLET, fakeApi, json, noContent, problem, renderApp, signedInRoutes } from "./test/fakeApi";

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

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
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

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
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
  it("keeps a plain user out of the admin console", async () => {
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([]) });

    renderApp("/admin/users");

    expect(await screen.findByRole("heading", { name: "No admin access" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("never shows admin links on the customer site, even to an admin", async () => {
    fakeApi({
      ...signedInRoutes({ ...USER, roles: ["ADMIN", "USER"] }),
      "GET /api/v1/wallets": () => json([WALLET]),
    });

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.queryByText(/admin/i)).not.toBeInTheDocument();
  });

  it("sends a signed-out visitor of the console to its own sign-in page", async () => {
    fakeApi({ "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") });

    renderApp("/admin/reviews");

    expect(await screen.findByRole("heading", { name: "FinCore Admin" })).toBeInTheDocument();
    expect(screen.queryByText("Create an account")).not.toBeInTheDocument();
  });

  it("opens the console on the review queue", async () => {
    fakeApi({
      ...signedInRoutes({ ...USER, roles: ["ADMIN", "USER"] }),
      "GET /api/v1/admin/reviews": () => json([]),
    });

    renderApp("/admin");

    expect(await screen.findByRole("heading", { name: "Fraud review queue" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
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
  const card = "9955123456789011";
  const recipientRoute = {
    "GET /api/v1/transfers/recipient": () =>
      json({ wallet_id: destination, currency: "UZS", display_name: "Bobur T.", own: false }),
  };

  /** Types the recipient's card number and waits for their name. */
  async function enterCard() {
    await userEvent.type(await screen.findByLabelText("To card number"), card);
    await screen.findByText("Bobur T.");
  }

  it("validates the amount before calling the API", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      ...recipientRoute,
      "GET /api/v1/wallets": () => json([WALLET]),
    });
    renderApp("/transfer");

    await enterCard();
    await userEvent.type(screen.getByLabelText(/Amount/), "10.555");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/at most 2 decimals/)).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/transfers")).toBe(false);
  });

  it("retries with the same Idempotency-Key and sends the amount as a string", async () => {
    let attempts = 0;
    const { requests } = fakeApi({
      ...signedInRoutes(),
      ...recipientRoute,
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

    await enterCard();
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
      ...recipientRoute,
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transactions": () => json([]),
      "POST /api/v1/transfers": () => json(created, 201),
    });
    renderApp("/transfer");

    for (let i = 0; i < 2; i += 1) {
      await enterCard();
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

  it("shows who a card number belongs to before anything can be sent", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      ...recipientRoute,
      "GET /api/v1/wallets": () => json([WALLET]),
    });
    renderApp("/transfer");

    const input = await screen.findByLabelText("To card number");
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();

    // Pasted with spaces: shown grouped, looked up as plain digits.
    await userEvent.click(input);
    await userEvent.paste("9955 1234 5678 9011");

    expect(await screen.findByText("Bobur T.")).toBeInTheDocument();
    expect(input).toHaveValue("9955 1234 5678 9011");
    expect(send).toBeEnabled();
    const lookup = requests.find((r) => r.path === "/api/v1/transfers/recipient");
    expect(lookup?.search).toBe("?card_number=9955123456789011");
  });

  it("catches a mistyped card number without asking the server", async () => {
    const { requests } = fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]) });
    renderApp("/transfer");

    await userEvent.type(await screen.findByLabelText("To card number"), "9955123456789012");

    expect(await screen.findByText(/a digit is wrong/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(requests.some((r) => r.path === "/api/v1/transfers/recipient")).toBe(false);
  });

  it("says when no wallet has the card number", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transfers/recipient": () => problem(404, "Recipient Not Found"),
    });
    renderApp("/transfer");

    await userEvent.type(await screen.findByLabelText("To card number"), card);

    expect(await screen.findByText(/No FinCore wallet can receive money/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("won't send to a card in another currency", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transfers/recipient": () =>
        json({ wallet_id: destination, currency: "USD", display_name: "Bobur T.", own: false }),
    });
    renderApp("/transfer");

    await userEvent.type(await screen.findByLabelText("To card number"), card);

    expect(await screen.findByText(/This card is a USD wallet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
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

describe("changing the password", () => {
  it("checks the repeat locally, then shows the API's verdict", async () => {
    let body: unknown = null;
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/users/me/sessions": () => json([]),
      "POST /api/v1/users/me/password": (request) => {
        body = request.body;
        return (request.body as { current_password: string }).current_password === "right-one"
          ? noContent()
          : problem(422, "Incorrect Password");
      },
    });
    renderApp("/settings");

    const current = await screen.findByLabelText("Current password");
    await userEvent.type(current, "wrong-one");
    await userEvent.type(screen.getByLabelText("New password"), "brand-new-pass");
    await userEvent.type(screen.getByLabelText(/^Repeat new password/), "different-pass");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("The two new passwords differ.")).toBeInTheDocument();
    expect(body).toBeNull();

    await userEvent.clear(screen.getByLabelText(/^Repeat new password/));
    await userEvent.type(screen.getByLabelText(/^Repeat new password/), "brand-new-pass");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    // A 422 is shown in place; the user stays signed in.
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect Password");
    expect(screen.getByRole("heading", { name: "Account" })).toBeInTheDocument();

    await userEvent.clear(current);
    await userEvent.type(current, "right-one");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/Every other device has been signed out/)).toBeInTheDocument();
    expect(body).toEqual({ current_password: "right-one", new_password: "brand-new-pass" });
  });
});

describe("password fields", () => {
  it("won't register when the two passwords differ", async () => {
    const { requests } = fakeApi({ "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") });
    renderApp("/register");

    await userEvent.type(await screen.findByLabelText("First name"), "Ada");
    await userEvent.type(screen.getByLabelText("Last name"), "Lovelace");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Phone"), "+998901112233");
    await userEvent.type(screen.getByLabelText("Password"), "analytical-1843");
    await userEvent.type(screen.getByLabelText(/^Repeat password/), "analytical-1842");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("The two passwords differ.")).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/auth/register")).toBe(false);
  });

  it("registers once both passwords match", async () => {
    const { requests } = fakeApi({
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/register": () => json(USER, 201),
    });
    renderApp("/register");

    await userEvent.type(await screen.findByLabelText("First name"), "Ada");
    await userEvent.type(screen.getByLabelText("Last name"), "Lovelace");
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Phone"), "+998901112233");
    await userEvent.type(screen.getByLabelText("Password"), "analytical-1843");
    await userEvent.type(screen.getByLabelText(/^Repeat password/), "analytical-1843");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Account created. Sign in to continue.")).toBeInTheDocument();
    const register = requests.find((r) => r.path === "/api/v1/auth/register");
    // The confirmation never leaves the browser.
    expect(register?.body).not.toHaveProperty("confirm_password");
  });

  it("shows and hides the password with the eye button", async () => {
    fakeApi({ "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") });
    renderApp("/login");

    const password = await screen.findByLabelText("Password");
    await userEvent.type(password, "secret-pass");
    expect(password).toHaveAttribute("type", "password");

    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("secret-pass");

    await userEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });
});

describe("assistant chat", () => {
  it("asks the assistant and shows the reply as plain text", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "POST /api/v1/assistant/chat": () =>
        json({ reply: "Sizda 1,250.00 UZS bor. <b>not html</b>" }),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Ask FinCore" }));
    await userEvent.type(screen.getByLabelText("Message"), "Balansim qancha?{Enter}");

    const reply = await screen.findByText(/Sizda 1,250.00 UZS bor/);
    expect(reply.textContent).toContain("<b>not html</b>");
    const sent = requests.find((r) => r.path === "/api/v1/assistant/chat");
    expect(sent?.body).toEqual({ messages: [{ role: "user", content: "Balansim qancha?" }] });
    expect(sent?.headers.authorization).toBe("Bearer access-1");
  });

  it("keeps the question to resend when the assistant is unavailable", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "POST /api/v1/assistant/chat": () =>
        problem(503, "Assistant Not Configured", "The assistant needs an API key."),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Ask FinCore" }));
    await userEvent.type(screen.getByLabelText("Message"), "hello{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("The assistant needs an API key.");
    expect(screen.getByLabelText("Message")).toHaveValue("hello");
  });

  it("is not part of the admin console", async () => {
    fakeApi({
      ...signedInRoutes({ ...USER, roles: ["ADMIN", "USER"] }),
      "GET /api/v1/admin/reviews": () => json([]),
    });
    renderApp("/admin/reviews");

    expect(await screen.findByRole("heading", { name: "Fraud review queue" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask FinCore" })).not.toBeInTheDocument();
  });
});

describe("staying signed in, and out, across reloads", () => {
  it("doesn't let a customer session open the admin console", async () => {
    // A customer cookie exists, but the console asks for its own session.
    const { requests } = fakeApi({
      "POST /api/v1/auth/refresh": (request) =>
        request.headers["x-refresh-token-transport"] === "cookie"
          ? json({ access_token: "access-1", refresh_token: null, expires_in: 900 })
          : problem(401, "Invalid Token"),
      "GET /api/v1/users/me": () => json({ ...USER, roles: ["ADMIN", "USER"] }),
    });

    renderApp("/admin/login");

    expect(await screen.findByRole("heading", { name: "FinCore Admin" })).toBeInTheDocument();
    const refresh = requests.find((r) => r.path === "/api/v1/auth/refresh");
    expect(refresh?.headers["x-refresh-token-transport"]).toBe("cookie-admin");
  });

  it("signs in to the console with its own session", async () => {
    const { requests } = fakeApi({
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/login": () =>
        json({ access_token: "admin-1", refresh_token: null, expires_in: 900 }),
      "GET /api/v1/users/me": () => json({ ...USER, roles: ["ADMIN", "USER"] }),
      "GET /api/v1/admin/reviews": () => json([]),
    });
    renderApp("/admin/login");

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Fraud review queue" })).toBeInTheDocument();
    const login = requests.find((r) => r.path === "/api/v1/auth/login");
    expect(login?.headers["x-refresh-token-transport"]).toBe("cookie-admin");
  });

  it("never shows the sign-in page just because the server didn't answer", async () => {
    let up = false;
    fakeApi({
      "POST /api/v1/auth/refresh": () =>
        up
          ? json({ access_token: "access-1", refresh_token: null, expires_in: 900 })
          : problem(502, "Bad Gateway"),
      "GET /api/v1/users/me": () => json(USER),
      "GET /api/v1/wallets": () => json([]),
    });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Can't reach FinCore" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in to FinCore" })).not.toBeInTheDocument();

    up = true;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();
  });

  it("stays signed out after a reload even if the sign-out request failed", async () => {
    const first = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "POST /api/v1/auth/logout": () => problem(503, "Service Unavailable"),
    });
    const view = renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
    expect(first.requests.filter((r) => r.path === "/api/v1/auth/logout").length).toBeGreaterThan(1);
    view.unmount();

    // "Reload": the refresh cookie would still work, but must not be used.
    const second = fakeApi({
      ...signedInRoutes(),
      "POST /api/v1/auth/logout": () => noContent(),
    });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
    expect(second.requests.some((r) => r.path === "/api/v1/auth/refresh")).toBe(false);
    expect(second.requests.some((r) => r.path === "/api/v1/auth/logout")).toBe(true);
  });

  it("an expired session still goes to the sign-in page", async () => {
    fakeApi({ "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") });

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
  });
});

describe("signing in with a phone number", () => {
  it("sends a phone number as phone and an address with @ as email", async () => {
    const { requests } = fakeApi({
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/login": () =>
        json({ access_token: "access-1", refresh_token: null, expires_in: 900 }),
      "GET /api/v1/users/me": () => json(USER),
      "GET /api/v1/wallets": () => json([]),
    });
    renderApp("/login");

    await userEvent.type(await screen.findByLabelText("Phone number or email"), " 90 123 45 67 ");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();
    const login = requests.find((r) => r.path === "/api/v1/auth/login");
    expect(login?.body).toEqual({ phone: "90 123 45 67", password: "correct-horse" });
  });
});

describe("signing out after inactivity", () => {
  const MINUTE = 60_000;

  it("asks to sign in again when coming back after the idle limit", async () => {
    localStorage.setItem("fincore:last-activity:customer", String(Date.now() - 16 * MINUTE));
    // The refresh cookie would still work - it must not be used.
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "POST /api/v1/auth/logout": () => noContent(),
    });

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/auth/refresh")).toBe(false);
    expect(requests.some((r) => r.path === "/api/v1/auth/logout")).toBe(true);
  });

  it("stays signed in when coming back within the idle limit", async () => {
    localStorage.setItem("fincore:last-activity:customer", String(Date.now() - 5 * MINUTE));
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([]) });

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();
  });

  it("signs out an open page left untouched", async () => {
    authTiming.idleTimeoutMs = 150;
    authTiming.idleCheckIntervalMs = 40;
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "POST /api/v1/auth/logout": () => noContent(),
    });

    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Hello, Ada" })).toBeInTheDocument();

    expect(
      await screen.findByRole("heading", { name: "Sign in to FinCore" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/auth/logout")).toBe(true);
    expect(localStorage.getItem("fincore:last-activity:customer")).toBeNull();
  });
});

describe("exchange rates", () => {
  it("converts between the chosen currencies", async () => {
    const { requests } = fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]) });
    renderApp("/");

    await screen.findByRole("button", { name: "Swap currencies" });
    const result = document.querySelector("output");
    expect(result).toHaveTextContent("1 USD = 12,000 UZS");

    await userEvent.clear(screen.getByLabelText("Amount"));
    await userEvent.type(screen.getByLabelText("Amount"), "100");
    await userEvent.selectOptions(screen.getByLabelText("From"), "EUR");
    expect(result).toHaveTextContent("100 EUR = 1,500,000 UZS");

    await userEvent.click(screen.getByRole("button", { name: "Swap currencies" }));
    expect(result).toHaveTextContent("100 UZS = 0.006667 EUR");

    // Public reference data: fetched without the customer's token.
    const rates = requests.find((r) => r.path === "/api/v1/rates");
    expect(rates?.headers.authorization).toBeUndefined();
  });

  it("lists popular currencies against the chosen one", async () => {
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([]) });
    renderApp("/");

    const row = await screen.findByRole("button", { name: /RUB/ });
    expect(row).toHaveTextContent("150 UZS");
    await userEvent.click(row);
    expect(screen.getByLabelText("From")).toHaveValue("RUB");
  });

  it("keeps the wallets usable when rates can't be loaded", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/rates": () => json({ ...RATES, result: "error" }),
    });
    renderApp("/");

    expect(await screen.findByText("1,250.00 UZS")).toBeInTheDocument();
    expect(await screen.findByText(/Exchange rates are unavailable/)).toBeInTheDocument();
  });
});

describe("notifications bell", () => {
  const received = {
    id: "66666666-6666-4666-8666-666666666666",
    type: "transfer.received",
    title: "Money received",
    body: "Aziza K. sent you 12,500.00 UZS.",
    created_at: "2026-10-05T09:00:00Z",
    read: false,
  };

  it("shows how many are unread, lists them, and marks them read when opened", async () => {
    let unread = 1;
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/notifications": () =>
        json({
          unread_count: unread,
          items: [{ ...received, read: unread === 0 }],
        }),
      "POST /api/v1/notifications/read": () => {
        unread = 0;
        return noContent();
      },
    });
    renderApp("/");

    const bell = await screen.findByRole("button", {
      name: "Notifications, 1 unread",
    });
    await userEvent.click(bell);

    const panel = await screen.findByRole("dialog", { name: "Notifications" });
    expect(within(panel).getByText("Money received")).toBeInTheDocument();
    expect(
      within(panel).getByText("Aziza K. sent you 12,500.00 UZS."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        requests.some((r) => r.path === "/api/v1/notifications/read"),
      ).toBe(true),
    );
    // The badge clears once the server agrees.
    expect(
      await screen.findByRole("button", { name: "Notifications" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(
      screen.queryByRole("dialog", { name: "Notifications" }),
    ).not.toBeInTheDocument();
  });

  it("opens empty without marking anything read", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
    });
    renderApp("/");

    await userEvent.click(
      await screen.findByRole("button", { name: "Notifications" }),
    );

    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/notifications/read")).toBe(
      false,
    );
  });
});

describe("history", () => {
  const base = {
    type: "TRANSFER",
    status: "COMPLETED",
    currency: "UZS",
    description: null,
    created_at: "2026-10-05T09:00:00Z",
    completed_at: "2026-10-05T09:00:01Z",
  };
  const incoming = {
    ...base,
    id: "77777777-7777-4777-8777-777777777777",
    reference: "TRF-IN",
    direction: "IN",
    counterparty_name: "Aziza K.",
    amount_minor: 1_250_000,
  };
  const outgoing = {
    ...base,
    id: "88888888-8888-4888-8888-888888888888",
    reference: "TRF-OUT",
    direction: "OUT",
    counterparty_name: "Bobur T.",
    amount_minor: 30_000,
  };

  it("lists money received as well as money sent, with who and which way", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/transactions": () =>
        json([
          incoming,
          outgoing,
          {
            ...outgoing,
            id: "99999999-9999-4999-8999-999999999999",
            reference: "TRF-FAILED",
            status: "FAILED",
            amount_minor: 5_000,
          },
        ]),
    });
    renderApp("/transactions");

    const receivedRow = (await screen.findByText("TRF-IN")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(receivedRow).getByText("Received")).toBeInTheDocument();
    expect(within(receivedRow).getByText("from Aziza K.")).toBeInTheDocument();
    expect(within(receivedRow).getByText(/\+/)).toHaveTextContent(
      "+12,500.00 UZS",
    );

    const sentRow = screen.getByText("TRF-OUT").closest("tr") as HTMLElement;
    expect(within(sentRow).getByText("Sent")).toBeInTheDocument();
    expect(within(sentRow).getByText("to Bobur T.")).toBeInTheDocument();
    expect(within(sentRow).getByText(/−/)).toHaveTextContent("−300.00 UZS");

    // Nothing left the wallet, so no minus sign.
    const failedRow = screen
      .getByText("TRF-FAILED")
      .closest("tr") as HTMLElement;
    expect(within(failedRow).getByText(/50\.00 UZS/)).toHaveTextContent(
      /^50\.00 UZS$/,
    );
  });

  it("opens a received transfer without asking for the sender's details", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      [`GET /api/v1/transactions/${incoming.id}`]: () => json(incoming),
    });
    renderApp(`/transactions/${incoming.id}`);

    expect(
      await screen.findByRole("heading", { name: "Money received" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Aziza K.")).toBeInTheDocument();
    // The transfer resource itself belongs to the sender (404 for anyone else).
    expect(requests.some((r) => r.path.startsWith("/api/v1/transfers/"))).toBe(
      false,
    );
  });
});

describe("banking news", () => {
  const article = {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    title: "Markaziy bank asosiy stavkani saqlab qoldi",
    summary: "Asosiy stavka 14 foiz darajasida qoldi. <b>not markup</b>",
    source: "cbu.uz",
    url: "https://cbu.uz/uz/press_center/news/1/",
    published_at: "2026-10-05T09:00:00Z",
    unread: true,
  };

  it("counts news in the bell's badge and opens an article inside the app", async () => {
    let unread = 1;
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/news": () =>
        json({ unread_count: unread, items: [{ ...article, unread: unread > 0 }] }),
      "POST /api/v1/news/read": () => {
        unread = 0;
        return noContent();
      },
      [`GET /api/v1/news/${article.id}`]: () => json(article),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));

    // Only news is new, so the bell opens on it, and seeing it marks it read.
    const panel = await screen.findByRole("dialog", { name: "Notifications" });
    expect(within(panel).getByRole("tab", { name: /News/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() => expect(requests.some((r) => r.path === "/api/v1/news/read")).toBe(true));
    // Activity had nothing unread: it is not marked.
    expect(requests.some((r) => r.path === "/api/v1/notifications/read")).toBe(false);

    await userEvent.click(within(panel).getByText(article.title));

    expect(await screen.findByRole("heading", { name: article.title })).toBeInTheDocument();
    // A feed's text is shown as text, never interpreted as markup.
    expect(screen.getByText(article.summary)).toBeInTheDocument();
    const original = screen.getByRole("link", { name: /Read the full article on cbu\.uz/ });
    expect(original).toHaveAttribute("href", article.url);
    expect(original).toHaveAttribute("target", "_blank");
    expect(original).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("switching tabs shows the customer's own activity again", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "GET /api/v1/news": () => json({ unread_count: 0, items: [{ ...article, unread: false }] }),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "News" }));
    expect(screen.getByText(article.title)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All news" })).toHaveAttribute("href", "/news");
  });

  it("lists every kept article on the news page", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/news": () => json({ unread_count: 0, items: [article] }),
    });
    renderApp("/news");

    expect(await screen.findByRole("heading", { name: "Banking & finance news" })).toBeInTheDocument();
    const card = (await screen.findByText(article.title)).closest("a");
    expect(card).toHaveAttribute("href", `/news/${article.id}`);
    expect(requests.some((r) => r.path === "/api/v1/news/read")).toBe(false);
  });
});

describe("forgot password", () => {
  const signedOut = { "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token") };

  it("emails a code, then sets a new password with it", async () => {
    const { requests } = fakeApi({
      ...signedOut,
      "POST /api/v1/auth/password-reset/request": () => json(null, 202),
      "POST /api/v1/auth/password-reset/confirm": () => noContent(),
    });
    renderApp("/login");

    await userEvent.click(await screen.findByRole("link", { name: "Forgot password?" }));
    await userEvent.type(screen.getByLabelText("Phone number or email"), "+998 90 111 22 33");
    await userEvent.click(screen.getByRole("button", { name: "Send code" }));

    // Never says whether the account exists.
    expect(await screen.findByText(/has a FinCore account, a code is on its way/)).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/request"))?.body).toEqual({
      phone: "+998 90 111 22 33",
    });

    await userEvent.type(screen.getByLabelText("Code from the email"), "493817");
    await userEvent.type(screen.getByLabelText("New password"), "brand-new-password");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "brand-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));

    expect(
      await screen.findByText("Password changed. Sign in with your new password."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sign in to FinCore" })).toBeInTheDocument();
    const confirm = requests.find((r) => r.path.endsWith("/confirm"));
    expect(confirm?.body).toEqual({
      phone: "+998 90 111 22 33",
      code: "493817",
      new_password: "brand-new-password",
    });
    // Nobody is signed in yet, so nothing carries a token.
    expect(confirm?.headers.authorization).toBeUndefined();
  });

  it("won't save two passwords that differ", async () => {
    const { requests } = fakeApi({
      ...signedOut,
      "POST /api/v1/auth/password-reset/request": () => json(null, 202),
    });
    renderApp("/forgot-password");

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send code" }));
    await userEvent.type(await screen.findByLabelText("Code from the email"), "493817");
    await userEvent.type(screen.getByLabelText("New password"), "brand-new-password");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "brand-new-passw0rd");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));

    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/request"))?.body).toEqual({
      email: "ada@example.com",
    });
    expect(requests.some((r) => r.path.endsWith("/confirm"))).toBe(false);
  });

  it("shows why a code was refused and can send another", async () => {
    const { requests } = fakeApi({
      ...signedOut,
      "POST /api/v1/auth/password-reset/request": () => json(null, 202),
      "POST /api/v1/auth/password-reset/confirm": () =>
        problem(422, "Invalid Or Expired Code", "The code is wrong or has expired."),
    });
    renderApp("/forgot-password");

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send code" }));
    await userEvent.type(await screen.findByLabelText("Code from the email"), "000000");
    await userEvent.type(screen.getByLabelText("New password"), "brand-new-password");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "brand-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid Or Expired Code");

    await userEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    await waitFor(() =>
      expect(requests.filter((r) => r.path.endsWith("/request"))).toHaveLength(2),
    );
  });

  it("says so when the server can't send email", async () => {
    fakeApi({
      ...signedOut,
      "POST /api/v1/auth/password-reset/request": () =>
        problem(503, "Password Reset Unavailable"),
    });
    renderApp("/forgot-password");

    await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Password Reset Unavailable");
    expect(screen.queryByLabelText("Code from the email")).not.toBeInTheDocument();
  });

  it("is not offered on the staff console's sign-in", async () => {
    fakeApi(signedOut);
    renderApp("/admin/login");

    expect(await screen.findByRole("heading", { name: "FinCore Admin" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Forgot password?" })).not.toBeInTheDocument();
  });
});

describe("editing the profile", () => {
  function routes(update: (body: Record<string, unknown>) => Response) {
    let current = { ...USER };
    return fakeApi({
      "POST /api/v1/auth/refresh": () =>
        json({ access_token: "access-1", refresh_token: null, expires_in: 900 }),
      "GET /api/v1/users/me": () => json(current),
      "GET /api/v1/users/me/sessions": () => json([]),
      "PATCH /api/v1/users/me": (request) => {
        const body = request.body as Record<string, unknown>;
        const response = update(body);
        if (response.ok) {
          current = { ...current, ...body, phone: "+998907654321" } as typeof USER;
          delete (current as Record<string, unknown>).current_password;
          return json(current);
        }
        return response;
      },
    });
  }

  it("saves a new name without asking for the password", async () => {
    const { requests } = routes(() => json({}));
    renderApp("/settings");

    const firstName = await screen.findByLabelText("First name");
    expect(firstName).toHaveValue("Ada");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await userEvent.clear(firstName);
    await userEvent.type(firstName, "Augusta");
    const form = firstName.closest("form") as HTMLElement;
    expect(within(form).queryByLabelText("Current password")).not.toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Save changes" }));

    expect(await within(form).findByText("Your details have been saved.")).toBeInTheDocument();
    const patch = requests.find((r) => r.method === "PATCH");
    expect(patch?.body).toMatchObject({ first_name: "Augusta", current_password: null });
    // The rest of the app shows the new name too.
    expect(await screen.findByText("Augusta Lovelace")).toBeInTheDocument();
  });

  it("asks for the current password once the email or phone differs", async () => {
    const { requests } = routes((body) =>
      body.current_password === "correct-horse"
        ? json({})
        : problem(422, "Incorrect Password"),
    );
    renderApp("/settings");

    const phone = await screen.findByLabelText("Phone number");
    const form = phone.closest("form") as HTMLElement;
    // Typed with spaces, it is still the same number: nothing to save.
    await userEvent.clear(phone);
    await userEvent.type(phone, "+998 90 111 22 33");
    expect(within(form).queryByLabelText("Current password")).not.toBeInTheDocument();

    await userEvent.clear(phone);
    await userEvent.type(phone, "+998 90 765 43 21");
    const password = within(form).getByLabelText("Current password");
    await userEvent.type(password, "wrong");
    await userEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Incorrect Password");

    await userEvent.clear(password);
    await userEvent.type(password, "correct-horse");
    await userEvent.click(within(form).getByRole("button", { name: "Save changes" }));

    expect(await within(form).findByText("Your details have been saved.")).toBeInTheDocument();
    // The number comes back the way the server stores it, and the password field is gone.
    expect(phone).toHaveValue("+998907654321");
    expect(within(form).queryByLabelText("Current password")).not.toBeInTheDocument();
    const patches = requests.filter((r) => r.method === "PATCH");
    expect(patches[1]?.body).toMatchObject({
      phone: "+998 90 765 43 21",
      current_password: "correct-horse",
    });
  });
});

describe("announcements", () => {
  const ADMIN = { ...USER, roles: ["USER", "ADMIN"] };
  const published = {
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    title: "Maintenance",
    body: "FinCore will be unavailable on Sunday.",
    created_by_user_id: ADMIN.id,
    created_at: "2026-10-06T09:00:00Z",
  };

  it("lets an admin publish to every customer and withdraw again", async () => {
    let items = [published];
    const { requests } = fakeApi({
      ...signedInRoutes(ADMIN),
      "GET /api/v1/admin/announcements": () => json(items),
      "POST /api/v1/admin/announcements": (request) => {
        const created = { ...published, id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", ...(request.body as object) };
        items = [created, ...items];
        return json(created, 201);
      },
      [`DELETE /api/v1/admin/announcements/${published.id}`]: () => {
        items = items.filter((item) => item.id !== published.id);
        return noContent();
      },
    });
    renderApp("/admin/announcements");

    expect(await screen.findByText("Maintenance")).toBeInTheDocument();
    const publish = screen.getByRole("button", { name: "Publish to all customers" });
    expect(publish).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Title"), "  New limits ");
    await userEvent.type(screen.getByLabelText("Message"), "Transfers are now faster.");
    await userEvent.click(publish);

    expect(await screen.findByText("Published to every customer.")).toBeInTheDocument();
    expect(requests.find((r) => r.method === "POST" && r.path.endsWith("/announcements"))?.body).toEqual({
      title: "New limits",
      body: "Transfers are now faster.",
    });
    expect(await screen.findByText("New limits")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("");

    const row = screen.getByText("Maintenance").closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Withdraw" }));
    await waitFor(() => expect(screen.queryByText("Maintenance")).not.toBeInTheDocument());
  });

  it("shows support staff the list but no way to publish or withdraw", async () => {
    fakeApi({
      ...signedInRoutes({ ...USER, roles: ["USER", "SUPPORT"] }),
      "GET /api/v1/admin/announcements": () => json([published]),
    });
    renderApp("/admin/announcements");

    expect(await screen.findByText("Maintenance")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
  });

  it("shows an announcement and a refund in the customer's bell", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([]),
      "GET /api/v1/notifications": () =>
        json({
          unread_count: 2,
          items: [
            { id: published.id, type: "announcement", title: published.title, body: published.body, params: null, created_at: published.created_at, read: false },
            { id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", type: "payment.refunded", title: "Refund received", body: "Your payment PAY-1 of 50.00 UZS was refunded by Choyxona.", params: { amount: "50.00 UZS", reference: "PAY-1", counterparty: "Choyxona", partial: false }, created_at: "2026-10-06T08:00:00Z", read: false },
          ],
        }),
      "POST /api/v1/notifications/read": () => noContent(),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 2 unread" }));

    const panel = await screen.findByRole("dialog", { name: "Notifications" });
    expect(within(panel).getByText("Maintenance")).toBeInTheDocument();
    expect(within(panel).getByText("FinCore will be unavailable on Sunday.")).toBeInTheDocument();
    expect(within(panel).getByText("Refund received")).toBeInTheDocument();
  });
});

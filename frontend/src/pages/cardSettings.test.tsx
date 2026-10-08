import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WALLET, fakeApi, json, noLimit, renderApp, signedInRoutes } from "../test/fakeApi";

const USD = {
  ...WALLET,
  id: "99999999-0000-4000-8000-000000000002",
  card_number: "9955987654321094",
  currency: "USD",
  is_primary: false,
};
const walletUrl = `/api/v1/wallets/${WALLET.id}`;
const limitUrl = `/api/v1/limits/${WALLET.id}`;

/** A wallet page whose wallet the test can change, as the server would. */
function walletPage(start: typeof WALLET, extra: Parameters<typeof fakeApi>[0] = {}) {
  let wallet = start;
  const api = fakeApi({
    ...signedInRoutes(),
    [`GET ${walletUrl}`]: () => json(wallet),
    [`GET ${walletUrl}/entries`]: () => json([]),
    "GET /api/v1/wallets": () => json([wallet]),
    [`PATCH ${walletUrl}`]: (request) => {
      wallet = { ...wallet, name: (request.body as { name: string | null }).name };
      return json(wallet);
    },
    [`POST ${walletUrl}/primary`]: () => json((wallet = { ...wallet, is_primary: true })),
    [`POST ${walletUrl}/block`]: () => json((wallet = { ...wallet, blocked: true })),
    [`POST ${walletUrl}/unblock`]: () => json((wallet = { ...wallet, blocked: false })),
    ...extra,
  });
  renderApp(`/wallets/${WALLET.id}`);
  return api;
}

describe("card settings", () => {
  it("names a card, and removes the name when the field is emptied", async () => {
    const { requests } = walletPage(WALLET);

    const name = await screen.findByLabelText("Name");
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled(); // nothing to save yet
    await userEvent.type(name, "  Salary ");
    await userEvent.click(save);

    expect(await screen.findByRole("heading", { level: 1, name: /Salary/ })).toBeInTheDocument();
    expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({ name: "Salary" });

    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { level: 1, name: /UZS wallet/ })).toBeInTheDocument();
    expect(requests.filter((r) => r.method === "PATCH")[1]?.body).toEqual({ name: null });
  });

  it("makes another card the main one", async () => {
    const { requests } = walletPage({ ...WALLET, is_primary: false });

    await userEvent.click(await screen.findByRole("button", { name: "Make this my main card" }));

    expect(await screen.findByText(/This is your main card/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make this my main card" })).toBeNull();
    expect(requests.some((r) => r.path === `${walletUrl}/primary`)).toBe(true);
  });

  it("blocks and unblocks a card", async () => {
    const { requests } = walletPage(WALLET);

    await userEvent.click(await screen.findByRole("button", { name: "Block this card" }));
    expect(await screen.findByText(/This card is blocked/)).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Unblock this card" }));
    expect(await screen.findByRole("button", { name: "Block this card" })).toBeInTheDocument();
    expect(requests.filter((r) => r.method === "POST").map((r) => r.path)).toEqual(
      expect.arrayContaining([`${walletUrl}/block`, `${walletUrl}/unblock`]),
    );
  });

  it("sets, shows and removes a daily limit", async () => {
    let limit = noLimit(WALLET.id);
    const { requests } = walletPage(WALLET, {
      [`GET ${limitUrl}`]: () => json(limit),
      [`PUT ${limitUrl}`]: (request) => {
        const { daily_limit } = request.body as { daily_limit: string | null };
        limit =
          daily_limit === null
            ? noLimit(WALLET.id)
            : { ...limit, daily_limit_minor: 50_000, spent_minor: 20_000, remaining_minor: 30_000 };
        return json(limit);
      },
    });

    expect(await screen.findByText(/No limit is set/)).toBeInTheDocument();
    const field = screen.getByLabelText("Limit (UZS)");
    await userEvent.type(field, "500.555");
    await userEvent.click(screen.getByRole("button", { name: "Set limit" }));
    expect(await screen.findByText(/at most 2 decimals/)).toBeInTheDocument();
    expect(requests.some((r) => r.method === "PUT")).toBe(false);

    await userEvent.clear(field);
    await userEvent.type(field, "500");
    await userEvent.click(screen.getByRole("button", { name: "Set limit" }));
    expect(
      await screen.findByText(
        "Limit 500.00 UZS. Sent in the last 24 hours: 200.00 UZS. You can still send 300.00 UZS.",
      ),
    ).toBeInTheDocument();
    expect(requests.find((r) => r.method === "PUT")?.body).toEqual({ daily_limit: "500" });

    await userEvent.click(screen.getByRole("button", { name: "Remove limit" }));
    expect(await screen.findByText(/No limit is set/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove limit" })).toBeNull();
  });

  it("shows the name, the main card and a blocked one in the wallet list", async () => {
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () =>
        json([
          { ...WALLET, name: "Salary" },
          { ...USD, blocked: true },
        ]),
    });
    renderApp("/");

    const salary = (await screen.findByText(/Salary/)).closest("a")!;
    expect(within(salary).getByText("Main")).toBeInTheDocument();
    const dollars = screen.getByText("9955 9876 5432 1094").closest("a")!;
    expect(within(dollars).getByText(/USD wallet/)).toBeInTheDocument();
    expect(within(dollars).getByText("Blocked")).toBeInTheDocument();
    expect(within(dollars).queryByText("Main")).toBeNull();
  });
});

describe("sending from a card with settings", () => {
  const recipient = {
    "GET /api/v1/transfers/recipient": () =>
      json({
        wallet_id: "33333333-3333-4333-8333-333333333333",
        currency: "UZS",
        display_name: "Bobur T.",
        own: false,
      }),
  };

  it("won't send from a blocked card, and says where to unblock it", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      ...recipient,
      "GET /api/v1/wallets": () => json([{ ...WALLET, name: "Salary", blocked: true }]),
    });
    renderApp("/transfer");

    expect(await screen.findByText(/This card is blocked, so nothing can leave it/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the card" })).toHaveAttribute(
      "href",
      `/wallets/${WALLET.id}`,
    );
    expect(screen.getByRole("option", { name: /^Salary · UZS · .* · blocked$/ })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("To card number"), "9955000000000014");
    await screen.findByText("Bobur T.");
    await userEvent.type(screen.getByLabelText(/Amount/), "10");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(requests.some((r) => r.path === "/api/v1/transfers" && r.method === "POST")).toBe(false);
  });

  it("stops an amount over what the daily limit has left", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      ...recipient,
      "GET /api/v1/wallets": () => json([WALLET]),
      [`GET ${limitUrl}`]: () =>
        json({
          ...noLimit(WALLET.id),
          daily_limit_minor: 50_000,
          spent_minor: 20_000,
          remaining_minor: 30_000,
        }),
    });
    renderApp("/transfer");

    await userEvent.type(await screen.findByLabelText("To card number"), "9955000000000014");
    await screen.findByText("Bobur T.");
    await waitFor(() => expect(requests.some((r) => r.path === limitUrl)).toBe(true));
    await userEvent.type(screen.getByLabelText(/Amount/), "300.01");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText(/over your daily limit for this card: you can still send 300.00 UZS/),
    ).toBeInTheDocument();
    expect(requests.some((r) => r.path === "/api/v1/transfers" && r.method === "POST")).toBe(false);
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../i18n";
import { WALLET, fakeApi, json, noContent, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const GOAL = {
  id: "dddddddd-0000-4000-8000-000000000001",
  name: "New phone",
  currency: "UZS",
  target_minor: 500_000,
  saved_minor: 125_000,
  created_at: "2026-10-12T10:00:00Z",
};
const USD = { ...WALLET, id: "99999999-0000-4000-8000-000000000009", currency: "USD" };
const movement = (overrides: Record<string, unknown> = {}) => ({
  id: "eeeeeeee-0000-4000-8000-000000000001",
  reference: "SAV-0001",
  goal_id: GOAL.id,
  wallet_id: WALLET.id,
  direction: "DEPOSIT",
  amount_minor: 30_000,
  currency: "UZS",
  status: "COMPLETED",
  failure_reason: null,
  created_at: "2026-10-12T11:00:00Z",
  completed_at: "2026-10-12T11:00:00Z",
  ...overrides,
});

/** A goals page whose goal the fake server changes as the real one would. */
function page(start = GOAL, extra: Parameters<typeof fakeApi>[0] = {}) {
  let goals = [start];
  const api = fakeApi({
    ...signedInRoutes(),
    "GET /api/v1/wallets": () => json([USD, WALLET]),
    "GET /api/v1/savings-goals": () => json(goals),
    [`GET /api/v1/savings-goals/${GOAL.id}/movements`]: () => json([]),
    [`POST /api/v1/savings-goals/${GOAL.id}/deposit`]: (request) => {
      const amount = Number((request.body as { amount: string }).amount) * 100;
      goals = [{ ...goals[0]!, saved_minor: goals[0]!.saved_minor + amount }];
      return json(movement({ amount_minor: amount }), 201);
    },
    [`POST /api/v1/savings-goals/${GOAL.id}/withdraw`]: (request) => {
      const amount = Number((request.body as { amount: string }).amount) * 100;
      goals = [{ ...goals[0]!, saved_minor: goals[0]!.saved_minor - amount }];
      return json(movement({ direction: "WITHDRAW", amount_minor: amount }), 201);
    },
    [`DELETE /api/v1/savings-goals/${GOAL.id}`]: () => {
      goals = [];
      return noContent();
    },
    ...extra,
  });
  renderApp("/goals");
  return api;
}

describe("savings goals", () => {
  it("shows how far along a goal is, in words and as a bar", async () => {
    page();

    const bar = await screen.findByRole("progressbar", {
      name: "New phone: 1,250.00 UZS of 5,000.00 UZS saved, 25%",
    });
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText(/1,250.00 UZS of 5,000.00 UZS · 3,750.00 UZS to go/)).toBeInTheDocument();
  });

  it("adds money from the card in the goal's currency", async () => {
    const { requests } = page();

    await userEvent.click(await screen.findByRole("button", { name: "Add money" }));
    // Only the UZS card can pay into a UZS goal.
    expect(within(screen.getByLabelText("From card")).getAllByRole("option")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("Amount (UZS)"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("300.00 UZS added to the goal.")).toBeInTheDocument();
    expect(
      await screen.findByRole("progressbar", { name: /1,550.00 UZS of 5,000.00 UZS saved, 31%/ }),
    ).toBeInTheDocument();
    const sent = requests.find((r) => r.path.endsWith("/deposit"));
    expect(sent?.body).toEqual({ wallet_id: WALLET.id, amount: "300" });
    expect(sent?.headers["idempotency-key"]).toBeTruthy();
  });

  it("won't ask for more than the goal holds", async () => {
    const { requests } = page();

    await userEvent.click(await screen.findByRole("button", { name: "Take money out" }));
    await userEvent.type(screen.getByLabelText("Amount (UZS)"), "1250.01");
    await userEvent.click(screen.getByRole("button", { name: "Take out" }));
    expect(screen.getByText("The goal holds 1,250.00 UZS.")).toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith("/withdraw"))).toBe(false);

    // (The field's label now carries the error too.)
    await userEvent.clear(screen.getByLabelText(/Amount \(UZS\)/));
    await userEvent.type(screen.getByLabelText(/Amount \(UZS\)/), "1250");
    await userEvent.click(screen.getByRole("button", { name: "Take out" }));
    expect(await screen.findByText("1,250.00 UZS is back on your card.")).toBeInTheDocument();
    // Empty now: it can be closed, on a second press.
    await userEvent.click(await screen.findByRole("button", { name: "Close goal" }));
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Confirm close" }));
    expect(await screen.findByText(/No goals yet/)).toBeInTheDocument();
  });

  it("says plainly when a movement failed or is still on its way", async () => {
    let answer = movement({ status: "FAILED", failure_reason: "Insufficient Funds" });
    setLang("uz");
    page(GOAL, {
      [`POST /api/v1/savings-goals/${GOAL.id}/deposit`]: () => json(answer, 201),
    });

    await userEvent.click(await screen.findByRole("button", { name: "Pul qo‘shish" }));
    await userEvent.type(screen.getByLabelText("Summa (UZS)"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Qo‘shish" }));
    expect(
      await screen.findByText("Hech narsa o‘tkazilmadi: Mablag‘ yetarli emas."),
    ).toBeInTheDocument();

    answer = movement({ status: "PENDING", completed_at: null });
    await userEvent.click(screen.getByRole("button", { name: "Pul qo‘shish" }));
    await userEvent.type(screen.getByLabelText("Summa (UZS)"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Qo‘shish" }));
    // In Uzbek an amount is written the local way.
    expect(await screen.findByText(/300,00 so‘m yo‘lda/)).toBeInTheDocument();
  });

  it("creates a goal, checking the target first", async () => {
    let goals: (typeof GOAL)[] = [];
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/savings-goals": () => json(goals),
      "POST /api/v1/savings-goals": () => {
        goals = [{ ...GOAL, saved_minor: 0 }];
        return json(goals[0], 201);
      },
      [`GET /api/v1/savings-goals/${GOAL.id}/movements`]: () => json([]),
    });
    renderApp("/goals");

    expect(await screen.findByText(/No goals yet/)).toBeInTheDocument();
    const create = screen.getByRole("button", { name: "Create goal" });
    expect(create).toBeDisabled(); // no name yet
    await userEvent.type(screen.getByLabelText("What for"), "New phone");
    await userEvent.type(screen.getByLabelText("How much it takes (UZS)"), "5000.555");
    await userEvent.click(create);
    expect(await screen.findByText(/at most 2 decimals/)).toBeInTheDocument();
    expect(requests.some((r) => r.method === "POST" && r.path === "/api/v1/savings-goals")).toBe(
      false,
    );

    await userEvent.clear(screen.getByLabelText(/How much it takes \(UZS\)/));
    await userEvent.type(screen.getByLabelText(/How much it takes \(UZS\)/), "5000");
    await userEvent.click(create);
    expect(await screen.findByRole("progressbar", { name: /saved, 0%/ })).toBeInTheDocument();
    expect(
      requests.find((r) => r.method === "POST" && r.path === "/api/v1/savings-goals")?.body,
    ).toEqual({ name: "New phone", currency: "UZS", target: "5000" });
    // An empty goal offers closing rather than taking out.
    expect(screen.queryByRole("button", { name: "Take money out" })).toBeNull();
  });

  it("lists what went in and out, and marks a reached goal", async () => {
    page(
      { ...GOAL, saved_minor: 600_000 },
      {
        [`GET /api/v1/savings-goals/${GOAL.id}/movements`]: () =>
          json([
            movement({ direction: "WITHDRAW", amount_minor: 10_000, id: "m2" }),
            movement({ status: "FAILED", failure_reason: "Wallet Blocked", id: "m3" }),
          ]),
      },
    );

    // Over the target still reads as 100%, not more.
    expect(await screen.findByRole("progressbar", { name: /saved, 100%/ })).toBeInTheDocument();
    expect(screen.getByText(/Reached!/)).toBeInTheDocument();
    const history = (await screen.findByText("Latest movements")).closest("details")!;
    await waitFor(() => expect(within(history).getAllByRole("listitem")).toHaveLength(2));
    expect(history).toHaveTextContent("Taken out");
    expect(history).toHaveTextContent("−100.00 UZS");
    expect(within(history).getByText("FAILED")).toBeInTheDocument();
  });

  it("shows the server's refusal and keeps the form", async () => {
    page(GOAL, {
      [`POST /api/v1/savings-goals/${GOAL.id}/deposit`]: () =>
        problem(503, "Savings Unavailable", "Savings can't be reached right now."),
    });

    await userEvent.click(await screen.findByRole("button", { name: "Add money" }));
    await userEvent.type(screen.getByLabelText("Amount (UZS)"), "300");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText(/Savings Unavailable/)).toBeInTheDocument();
    expect(screen.getByLabelText("Amount (UZS)")).toHaveValue("300");
  });
});

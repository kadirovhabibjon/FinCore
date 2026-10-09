import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../i18n";
import { WALLET, fakeApi, json, renderApp, signedInRoutes } from "../test/fakeApi";

const row = (reference: string, overrides: Record<string, unknown> = {}) => ({
  id: `77777777-7777-4777-8777-${reference.replace(/[^0-9a-f]/gi, "0").padStart(12, "0").slice(-12)}`,
  type: "TRANSFER",
  direction: "OUT",
  counterparty_name: "Bobur T.",
  reference,
  status: "COMPLETED",
  amount_minor: 10_000,
  currency: "UZS",
  description: null,
  created_at: "2026-10-09T09:00:00Z",
  completed_at: "2026-10-09T09:00:00Z",
  ...overrides,
});

/** A history the fake server filters the way the real one would. */
function history() {
  const all = [
    row("TRF-SENT", { id: "77777777-7777-4777-8777-000000000001" }),
    row("TRF-GOT", {
      id: "77777777-7777-4777-8777-000000000002",
      direction: "IN",
      counterparty_name: "Aziza K.",
    }),
    row("PAY-SHOP", {
      id: "77777777-7777-4777-8777-000000000003",
      type: "PAYMENT",
      counterparty_name: null,
      description: "Coffee",
    }),
  ];
  return fakeApi({
    ...signedInRoutes(),
    "GET /api/v1/wallets": () => json([WALLET]),
    "GET /api/v1/transactions": (request) => {
      const query = new URLSearchParams(request.search);
      return json(
        all.filter(
          (item) =>
            (!query.get("type") || item.type === query.get("type")) &&
            (!query.get("direction") || item.direction === query.get("direction")) &&
            (!query.get("q") ||
              JSON.stringify(item).toLowerCase().includes(query.get("q")!.toLowerCase())),
        ),
      );
    },
  });
}

const asked = (requests: { path: string; search: string }[]) =>
  requests
    .filter((r) => r.path === "/api/v1/transactions")
    .map((r) => {
      const query = new URLSearchParams(r.search);
      query.delete("limit");
      query.delete("offset");
      return query.toString();
    });

describe("filtering the history", () => {
  it("narrows by what kind of operation it was", async () => {
    const { requests } = history();
    renderApp("/transactions");
    expect(await screen.findByText("TRF-SENT")).toBeInTheDocument();
    expect(screen.getByText("PAY-SHOP")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Show"), "Money received");
    await waitFor(() => expect(screen.queryByText("TRF-SENT")).toBeNull());
    expect(screen.getByText("TRF-GOT")).toBeInTheDocument();
    expect(asked(requests)).toContain("direction=IN");

    await userEvent.selectOptions(screen.getByLabelText("Show"), "Transfers sent");
    await waitFor(() => expect(screen.queryByText("TRF-GOT")).toBeNull());
    expect(asked(requests)).toContain("type=TRANSFER&direction=OUT");

    await userEvent.selectOptions(screen.getByLabelText("Show"), "Payments");
    expect(await screen.findByText("PAY-SHOP")).toBeInTheDocument();
    expect(asked(requests)).toContain("type=PAYMENT");
  });

  it("searches once the typing pauses, not on every key", async () => {
    const { requests } = history();
    renderApp("/transactions");
    await screen.findByText("TRF-SENT");

    await userEvent.type(screen.getByLabelText("Search"), "aziza");
    await waitFor(() => expect(screen.queryByText("TRF-SENT")).toBeNull());
    expect(screen.getByText("TRF-GOT")).toBeInTheDocument();
    const searches = asked(requests).filter((query) => query.startsWith("q="));
    expect(searches).toEqual(["q=aziza"]);
  });

  it("says when nothing matches, and clears back to everything", async () => {
    history();
    renderApp("/transactions");
    await screen.findByText("TRF-SENT");

    await userEvent.type(screen.getByLabelText("Search"), "nobody");
    expect(await screen.findByText("Nothing matches these filters.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("TRF-SENT")).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  it("opens already filtered from a link, dates included", async () => {
    const { requests } = history();
    renderApp("/transactions?show=payments&from=2026-10-01&to=2026-10-09&q=coffee");

    expect(await screen.findByText("PAY-SHOP")).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("coffee");
    expect(screen.getByLabelText("Show")).toHaveValue("payments");
    expect(screen.getByLabelText("From")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-10-09");
    expect(asked(requests)[0]).toBe(
      "type=PAYMENT&q=coffee&date_from=2026-10-01&date_to=2026-10-09",
    );
  });

  it("downloads what is filtered, not everything", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transactions": () => json([row("PAY-SHOP", { type: "PAYMENT" })]),
      "GET /api/v1/transactions/export.csv": () =>
        new Response("date_utc,type\r\n", {
          status: 200,
          headers: {
            "Content-Type": "text/csv",
            "Content-Disposition": 'attachment; filename="fincore-history.csv"',
          },
        }),
    });
    URL.createObjectURL = () => "blob:test";
    URL.revokeObjectURL = () => undefined;
    renderApp("/transactions?show=payments");

    await userEvent.click(await screen.findByRole("button", { name: "Download these as CSV" }));
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/export.csv"))).toBe(true));
    expect(requests.find((r) => r.path.endsWith("/export.csv"))!.search).toBe("?type=PAYMENT");
  });
});

describe("what the money went on", () => {
  const stats = {
    months: ["2026-10"],
    currencies: [
      {
        currency: "UZS",
        total_in_minor: 0,
        total_out_minor: 2_545_000,
        months: [{ month: "2026-10", in_minor: 0, out_minor: 2_545_000 }],
      },
    ],
  };
  const spending = {
    months: ["2026-10"],
    currencies: [
      {
        currency: "UZS",
        total_minor: 2_545_000,
        categories: [
          { category: "MOBILE", amount_minor: 2_500_000, count: 1 },
          { category: "SHOPS", amount_minor: 35_000, count: 2 },
          { category: "TRANSFERS", amount_minor: 10_000, count: 1 },
        ],
      },
    ],
  };
  const routes = (answer: unknown = spending) => ({
    ...signedInRoutes(),
    "GET /api/v1/wallets": () => json([WALLET]),
    "GET /api/v1/transactions/stats": () => json(stats),
    "GET /api/v1/transactions/stats/categories": () => json(answer),
  });

  it("lists the categories largest first, with amounts and shares in words", async () => {
    const { requests } = fakeApi(routes());
    renderApp("/stats");

    const list = await screen.findByRole("list", { name: "Spending by category" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((item) => item.getAttribute("aria-label"))).toEqual([
      "Mobile: 25,000.00 UZS, 98% of spending, 1 operations",
      "Shops: 350.00 UZS, 1% of spending, 2 operations",
      // Under one percent is said to be so, not rounded to nothing.
      "Transfers to people: 100.00 UZS, <1% of spending, 1 operations",
    ]);
    expect(screen.getByRole("heading", { name: "Where the money went, UZS" })).toBeInTheDocument();
    expect(screen.getByText("25,450.00 UZS", { selector: "strong" })).toBeInTheDocument();
    // The same period the page's other numbers are for.
    const query = requests.find((r) => r.path.endsWith("/stats/categories"))!.search;
    expect(new URLSearchParams(query).get("months")).toBe("6");
  });

  it("follows the chosen period, and the language", async () => {
    const { requests } = fakeApi(routes());
    setLang("uz");
    renderApp("/stats");

    const list = await screen.findByRole("list", { name: "Toifalar bo‘yicha xarajat" });
    expect(within(list).getByText("Mobil aloqa")).toBeInTheDocument();
    expect(within(list).getByText("Do‘konlar")).toBeInTheDocument();

    const period = screen.getAllByRole("combobox").find((select) =>
      within(select).queryByRole("option", { name: /12/ }),
    ) as HTMLElement;
    await userEvent.selectOptions(period, "12");
    await waitFor(() =>
      expect(
        requests.some(
          (r) =>
            r.path.endsWith("/stats/categories") &&
            new URLSearchParams(r.search).get("months") === "12",
        ),
      ).toBe(true),
    );
  });

  it("says so when nothing was spent", async () => {
    fakeApi(routes({ months: ["2026-10"], currencies: [] }));
    renderApp("/stats");

    expect(await screen.findByText("Nothing was spent in this period.")).toBeInTheDocument();
  });
});

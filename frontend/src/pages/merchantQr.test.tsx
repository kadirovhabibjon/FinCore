import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { merchantFromScan, merchantLink } from "../lib/qr";
import { WALLET, fakeApi, json, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const MERCHANT = "3f2b8c1e-0000-4000-8000-000000000001";
const shop = { id: MERCHANT, name: "Chorsu Coffee", active: true };

describe("a merchant's QR code", () => {
  it("is a link to the pay form, with an amount only when it is a plain number", () => {
    expect(merchantLink("https://fin.example", MERCHANT)).toBe(
      `https://fin.example/pay/merchant?merchant=${MERCHANT}`,
    );
    expect(merchantLink("https://fin.example", MERCHANT, " 25000.50 ")).toBe(
      `https://fin.example/pay/merchant?merchant=${MERCHANT}&amount=25000.50`,
    );
    expect(merchantLink("https://fin.example", MERCHANT, "a lot")).toBe(
      `https://fin.example/pay/merchant?merchant=${MERCHANT}`,
    );
  });

  it("is read back from a link on any host, or from the bare id", () => {
    expect(merchantFromScan(merchantLink("https://fin.example", MERCHANT, "1200"))).toEqual({
      merchantId: MERCHANT,
      amount: "1200",
    });
    expect(merchantFromScan(`  ${MERCHANT.toUpperCase()} `)).toEqual({
      merchantId: MERCHANT,
      amount: "",
    });
    // An amount that is not a plain number is dropped, not trusted.
    expect(
      merchantFromScan(`https://x.test/pay/merchant?merchant=${MERCHANT}&amount=1e9`),
    ).toEqual({ merchantId: MERCHANT, amount: "" });
    for (const other of [
      "",
      "hello",
      "https://x.test/transfer?to=9955123456789011",
      "https://x.test/pay/merchant?merchant=not-an-id",
      "9955123456789011",
    ]) {
      expect(merchantFromScan(other), other).toBeNull();
    }
  });
});

describe("the merchant's page", () => {
  it("shows a QR code for the counter, with the amount if one is set", async () => {
    fakeApi({
      ...signedInRoutes(),
      [`GET /api/v1/merchants/${MERCHANT}`]: () =>
        json({
          id: MERCHANT,
          owner_user_id: "11111111-1111-4111-8111-111111111111",
          name: "Chorsu Coffee",
          status: "ACTIVE",
          created_at: "2026-10-01T10:00:00Z",
        }),
      [`GET /api/v1/merchants/${MERCHANT}/payments`]: () => json([]),
      "GET /api/v1/webhooks/endpoints": () => json([]),
    });
    renderApp(`/merchants/${MERCHANT}`);

    const toggle = await screen.findByRole("button", { name: "Show payment QR code" });
    // (The picture itself can't be drawn in the test browser; its
    // caption stands in for it, as in the card's own QR test.)
    expect(screen.queryByText(/A customer scans this/)).toBeNull();
    await userEvent.click(toggle);

    expect(await screen.findByText(/A customer scans this/)).toBeInTheDocument();
    expect(screen.queryByText(/It asks for/)).toBeNull();
    await userEvent.type(screen.getByLabelText("Amount to ask for (optional)"), "25000");
    expect(screen.getByText(/It asks for 25000; the customer can still change it/)).toBeInTheDocument();
    // Not a plain number: no amount is put in the code.
    await userEvent.type(screen.getByLabelText("Amount to ask for (optional)"), "abc");
    expect(screen.queryByText(/It asks for/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Hide QR code" }));
    expect(screen.queryByText(/A customer scans this/)).toBeNull();
  });
});

describe("paying a merchant", () => {
  const base = () => ({
    ...signedInRoutes(),
    "GET /api/v1/wallets": () => json([WALLET]),
  });

  it("opens from the merchant's code with the shop named and the amount filled in", async () => {
    const { requests } = fakeApi({
      ...base(),
      [`GET /api/v1/merchants/${MERCHANT}/public`]: () => json(shop),
    });
    renderApp(`/pay/merchant?merchant=${MERCHANT}&amount=25000`);

    expect(await screen.findByText("Chorsu Coffee")).toBeInTheDocument();
    expect(screen.getByLabelText("Merchant id")).toHaveValue(MERCHANT);
    expect(screen.getByLabelText(/Amount/)).toHaveValue("25000");
    expect(screen.getByRole("button", { name: "Pay" })).toBeEnabled();
    // Opening the link pays nothing.
    expect(requests.some((r) => r.method === "POST" && r.path === "/api/v1/payments")).toBe(false);
  });

  it("looks the merchant up only once the id is whole", async () => {
    const { requests } = fakeApi({
      ...base(),
      [`GET /api/v1/merchants/${MERCHANT}/public`]: () => json(shop),
    });
    renderApp("/pay/merchant");

    const field = await screen.findByLabelText("Merchant id");
    expect(screen.getByText(/The id the merchant gave you/)).toBeInTheDocument();
    await userEvent.type(field, MERCHANT.slice(0, 20));
    expect(requests.some((r) => r.path.endsWith("/public"))).toBe(false);
    await userEvent.type(field, MERCHANT.slice(20));

    expect(await screen.findByText("Chorsu Coffee")).toBeInTheDocument();
    expect(requests.filter((r) => r.path.endsWith("/public"))).toHaveLength(1);
  });

  it("won't pay an id that is nobody's, or a merchant that can't be paid", async () => {
    let answer = () => problem(404, "Merchant Not Found");
    const { requests } = fakeApi({
      ...base(),
      [`GET /api/v1/merchants/${MERCHANT}/public`]: () => answer(),
    });
    renderApp(`/pay/merchant?merchant=${MERCHANT}&amount=100`);

    expect(await screen.findByText("There is no merchant with this id.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay" })).toBeDisabled();

    answer = () => json({ ...shop, active: false });
    const other = MERCHANT.replace(/1$/, "2");
    fakeApi({
      ...base(),
      [`GET /api/v1/merchants/${other}/public`]: () => json({ ...shop, id: other, active: false }),
    });
    await userEvent.clear(screen.getByLabelText("Merchant id"));
    await userEvent.type(screen.getByLabelText("Merchant id"), other);
    expect(
      await screen.findByText("This merchant can't take payments right now."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay" })).toBeDisabled();
    expect(requests.some((r) => r.method === "POST" && r.path === "/api/v1/payments")).toBe(false);
  });

  it("can still be paid when the name can't be looked up", async () => {
    fakeApi({
      ...base(),
      [`GET /api/v1/merchants/${MERCHANT}/public`]: () => problem(503, "Service Unavailable"),
    });
    renderApp(`/pay/merchant?merchant=${MERCHANT}`);

    expect(await screen.findByText(/Couldn't look up this merchant right now/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Pay" })).toBeEnabled());
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { isCompletePhone, phoneDigits } from "../lib/phone";
import { WALLET, fakeApi, json, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const destination = "33333333-3333-4333-8333-333333333333";
const found = () =>
  json({
    wallet_id: destination,
    currency: "UZS",
    display_name: "Bobur T.",
    own: false,
    card_last4: "4188",
  });

async function choosePhone() {
  await userEvent.click(await screen.findByRole("button", { name: "Phone number" }));
  return screen.getByLabelText("To phone number");
}

describe("phone numbers", () => {
  it("knows a whole number from a half-typed one", () => {
    expect(phoneDigits("+998 90 123-45-67")).toBe("998901234567");
    expect(phoneDigits("00998901234567")).toBe("998901234567");
    for (const whole of ["901234567", "+998 90 123 45 67", "998901234567", "+7 912 345 67 89"]) {
      expect(isCompletePhone(whole), whole).toBe(true);
    }
    for (const partial of ["", "90123", "+99890123456", "+9989012345678", "1234567"]) {
      expect(isCompletePhone(partial), partial).toBe(false);
    }
  });
});

describe("sending to a phone number", () => {
  it("looks the number up once it is whole, in the currency being sent", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transfers/recipient": found,
    });
    renderApp("/transfer");

    const field = await choosePhone();
    await userEvent.type(field, "+998 90 123");
    expect(screen.getByText(/The phone number the recipient registered/)).toBeInTheDocument();
    await userEvent.type(field, " 45 67");

    expect(await screen.findByText("Bobur T.")).toBeInTheDocument();
    expect(screen.getByText(/card ···· 4188/)).toBeInTheDocument();
    const lookups = requests.filter((r) => r.path === "/api/v1/transfers/recipient");
    // Not once per keystroke: only the finished number was asked about.
    expect(lookups).toHaveLength(1);
    expect(new URLSearchParams(lookups[0]!.search).get("phone")).toBe("+998 90 123 45 67");
    expect(new URLSearchParams(lookups[0]!.search).get("currency")).toBe("UZS");
    expect(new URLSearchParams(lookups[0]!.search).has("card_number")).toBe(false);
  });

  it("sends to the wallet the number led to", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transactions": () => json([]),
      "GET /api/v1/transfers/recipient": found,
      "POST /api/v1/transfers": () =>
        json(
          {
            id: "44444444-4444-4444-8444-444444444444",
            reference: "TRF-PHONE",
            source_wallet_id: WALLET.id,
            destination_wallet_id: destination,
            amount_minor: 1000,
            currency: "UZS",
            status: "COMPLETED",
            failure_reason: null,
            fraud_decision: "ALLOW",
            description: null,
            created_at: "2026-10-08T10:00:00Z",
            updated_at: "2026-10-08T10:00:00Z",
            completed_at: "2026-10-08T10:00:00Z",
          },
          201,
        ),
    });
    renderApp("/transfer");

    await userEvent.type(await choosePhone(), "901234567");
    await screen.findByText("Bobur T.");
    await userEvent.type(screen.getByLabelText(/Amount/), "10");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("To Bobur T. · 901234567")).toBeInTheDocument();
    const sent = requests.find((r) => r.method === "POST" && r.path === "/api/v1/transfers");
    expect(sent?.body).toMatchObject({ destination_wallet_id: destination, amount: "10" });
  });

  it("says when nobody can receive at the number, and when it is not a number", async () => {
    let answer = () => problem(404, "Recipient Not Found");
    fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transfers/recipient": () => answer(),
    });
    renderApp("/transfer");

    const field = await choosePhone();
    await userEvent.type(field, "901234567");
    expect(await screen.findByText(/Nobody can receive UZS at this phone number/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    answer = () => problem(422, "Invalid Phone Number");
    await userEvent.clear(field);
    await userEvent.type(field, "+1 000 000 00");
    expect(await screen.findByText(/Check the phone number/)).toBeInTheDocument();
  });

  it("keeps the card number and the phone number apart", async () => {
    const { requests } = fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/wallets": () => json([WALLET]),
      "GET /api/v1/transfers/recipient": found,
    });
    renderApp("/transfer");

    await userEvent.type(await choosePhone(), "901234567");
    await screen.findByText("Bobur T.");
    await userEvent.click(screen.getByRole("button", { name: "Card number" }));

    // Back on the card field: nobody is chosen until a card is typed.
    expect(screen.getByLabelText("To card number")).toHaveValue("");
    expect(screen.queryByText("Bobur T.")).toBeNull();
    expect(screen.getByRole("button", { name: "Scan QR code" })).toBeInTheDocument();
    await waitFor(() =>
      expect(requests.filter((r) => r.path === "/api/v1/transfers/recipient")).toHaveLength(1),
    );
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { USER, WALLET, fakeApi, json, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const CHALLENGE = {
  two_factor_required: true,
  challenge_id: "cccccccc-0000-4000-8000-000000000001",
  email_hint: "ad***@example.com",
  expires_in: 600,
};
const TOKENS = { access_token: "access-1", refresh_token: null, expires_in: 900 };

/** A browser with no session: the refresh cookie is not there. */
const signedOut = () => ({
  "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
});

async function enterPassword() {
  await userEvent.type(await screen.findByLabelText("Phone number or email"), "ada@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct-horse");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("signing in with two steps", () => {
  it("asks for the emailed code after the password, and signs in with it", async () => {
    let signedIn = false;
    const { requests } = fakeApi({
      ...signedOut(),
      "POST /api/v1/auth/login": () => json(CHALLENGE, 202),
      "POST /api/v1/auth/login/verify": () => {
        signedIn = true;
        return json(TOKENS);
      },
      "GET /api/v1/users/me": () => (signedIn ? json(USER) : problem(401, "Invalid Token")),
      "GET /api/v1/wallets": () => json([WALLET]),
    });
    renderApp("/login");

    await enterPassword();
    expect(await screen.findByRole("heading", { name: "Enter the code" })).toBeInTheDocument();
    expect(screen.getByText(/We emailed a 6-digit code to ad\*\*\*@example.com/)).toBeInTheDocument();
    // The password form is gone, and so is what was typed into it.
    expect(screen.queryByLabelText("Password")).toBeNull();
    expect(screen.getByLabelText("Code from the email")).toHaveValue("");

    await userEvent.type(screen.getByLabelText("Code from the email"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByText("9955 0000 0000 0006")).toBeInTheDocument();
    const verify = requests.find((r) => r.path === "/api/v1/auth/login/verify");
    expect(verify?.body).toEqual({ challenge_id: CHALLENGE.challenge_id, code: "123456" });
    // The same cookie transport as the first step: the session is the browser's.
    expect(verify?.headers["x-refresh-token-transport"]).toBe("cookie");
  });

  it("says a wrong code is wrong, and goes back to the password for a new one", async () => {
    fakeApi({
      ...signedOut(),
      "POST /api/v1/auth/login": () => json(CHALLENGE, 202),
      "POST /api/v1/auth/login/verify": () =>
        problem(401, "Invalid Or Expired Code", "The code is wrong or has expired."),
    });
    renderApp("/login");

    await enterPassword();
    await userEvent.type(await screen.findByLabelText("Code from the email"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText(/Invalid Or Expired Code/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Back to sign-in" }));
    expect(await screen.findByLabelText("Password")).toHaveValue("");
    expect(screen.queryByText(/Invalid Or Expired Code/)).toBeNull();
  });

  it("signs in at once when the account has no second step", async () => {
    let signedIn = false;
    fakeApi({
      ...signedOut(),
      "POST /api/v1/auth/login": () => {
        signedIn = true;
        return json(TOKENS);
      },
      "GET /api/v1/users/me": () => (signedIn ? json(USER) : problem(401, "Invalid Token")),
      "GET /api/v1/wallets": () => json([WALLET]),
    });
    renderApp("/login");

    await enterPassword();
    expect(await screen.findByText("9955 0000 0000 0006")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Enter the code" })).toBeNull();
  });
});

describe("two-step sign-in on the Account page", () => {
  function accountPage(start: boolean, extra: Parameters<typeof fakeApi>[0] = {}) {
    let enabled = start;
    const me = () => ({ ...USER, two_factor_enabled: enabled });
    return fakeApi({
      ...signedInRoutes(),
      "GET /api/v1/users/me": () => json(me()),
      "GET /api/v1/users/me/sessions": () => json([]),
      "POST /api/v1/users/me/two-factor/enable": () => json(CHALLENGE, 202),
      "POST /api/v1/users/me/two-factor/confirm": () => {
        enabled = true;
        return json(me());
      },
      "POST /api/v1/users/me/two-factor/disable": () => {
        enabled = false;
        return json(me());
      },
      ...extra,
    });
  }

  it("turns on with the password and then the code from the mailbox", async () => {
    const { requests } = accountPage(false);
    renderApp("/settings");

    expect(await screen.findByText(/Off\. Signing in takes only your password/)).toBeInTheDocument();
    const turnOn = screen.getByRole("button", { name: "Turn on" });
    expect(turnOn).toBeDisabled(); // no password yet
    await userEvent.type(screen.getByLabelText("Your password"), "correct-horse");
    await userEvent.click(turnOn);

    expect(
      await screen.findByText(/We emailed a code to ad\*\*\*@example.com/),
    ).toBeInTheDocument();
    // Asked, not yet on.
    expect(requests.some((r) => r.path.endsWith("/two-factor/confirm"))).toBe(false);
    await userEvent.type(screen.getByLabelText("Code from the email"), "654321");
    await userEvent.click(screen.getByRole("button", { name: "Confirm and turn on" }));

    expect(await screen.findByText("Two-step sign-in is on.")).toBeInTheDocument();
    expect(await screen.findByText(/On\. Signing in takes your password and a code/)).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/two-factor/enable"))?.body).toEqual({
      current_password: "correct-horse",
    });
    expect(requests.find((r) => r.path.endsWith("/two-factor/confirm"))?.body).toEqual({
      challenge_id: CHALLENGE.challenge_id,
      code: "654321",
    });
  });

  it("can be called off before the code is given, with nothing changed", async () => {
    const { requests } = accountPage(false);
    renderApp("/settings");

    await userEvent.type(
      await screen.findByLabelText("Your password"),
      "correct-horse",
    );
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(await screen.findByText(/Off\. Signing in takes only your password/)).toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith("/two-factor/confirm"))).toBe(false);
  });

  it("turns off with the password", async () => {
    const { requests } = accountPage(true);
    renderApp("/settings");

    expect(
      await screen.findByText(/On\. Signing in takes your password and a code emailed to ada@example.com/),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: "Turn off" }));

    expect(await screen.findByText("Two-step sign-in is off.")).toBeInTheDocument();
    await waitFor(() =>
      expect(requests.find((r) => r.path.endsWith("/two-factor/disable"))?.body).toEqual({
        current_password: "correct-horse",
      }),
    );
  });

  it("says why when no code can be emailed", async () => {
    accountPage(false, {
      "POST /api/v1/users/me/two-factor/enable": () =>
        problem(503, "Two-Step Sign-In Unavailable", "A code can't be emailed to this account."),
    });
    renderApp("/settings");

    await userEvent.type(
      await screen.findByLabelText("Your password"),
      "correct-horse",
    );
    await userEvent.click(screen.getByRole("button", { name: "Turn on" }));

    expect(await screen.findByText(/Two-Step Sign-In Unavailable/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Code from the email")).toBeNull();
  });
});

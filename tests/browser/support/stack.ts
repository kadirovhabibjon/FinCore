import { randomBytes, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Setting up what a test needs straight through the API: a browser test
// should spend its time on the screen it is about, not on signing up
// through three other screens first.

const BASE = process.env.FINCORE_URL ?? "http://localhost:8180";
const LEDGER = process.env.FINCORE_LEDGER_URL ?? "http://localhost:8092";

function ledgerToken(): string {
  if (process.env.FINCORE_LEDGER_TOKEN) return process.env.FINCORE_LEDGER_TOKEN;
  const env = fileURLToPath(new URL("../../../services/ledger-service/.env", import.meta.url));
  const line = readFileSync(env, "utf8")
    .split("\n")
    .find((row) => row.startsWith("INTERNAL_SERVICE_TOKEN="));
  if (!line) throw new Error("no INTERNAL_SERVICE_TOKEN in services/ledger-service/.env");
  return line.slice("INTERNAL_SERVICE_TOKEN=".length).trim();
}

async function call<T>(url: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  const response = await fetch(url, { ...init, headers: { ...headers, ...(init.headers as object) } });
  if (!response.ok) throw new Error(`${init.method ?? "GET"} ${url}: ${response.status} ${await response.text()}`);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export type Customer = {
  email: string;
  phone: string;
  password: string;
  firstName: string;
  token: string;
};

export type Wallet = { id: string; card_number: string; currency: string };

/** A new customer, signed up and signed in through the API. Each test
 * gets its own: nothing one test does can show up in another. */
export async function newCustomer(firstName = "Browser", lastName = "Test"): Promise<Customer> {
  const email = `browser-${randomBytes(6).toString("hex")}@example.com`;
  const password = `Br-${randomBytes(9).toString("base64url")}1!`;
  for (let attempt = 0; ; attempt++) {
    // A random number can be one an earlier run took: draw again.
    const phone = `+99890${String(randomBytes(4).readUInt32BE() % 10_000_000).padStart(7, "0")}`;
    try {
      await call(`${BASE}/api/v1/auth/register`, {
        method: "POST",
        body: JSON.stringify({ email, phone, password, first_name: firstName, last_name: lastName }),
      });
      const { access_token: token } = await call<{ access_token: string }>(
        `${BASE}/api/v1/auth/login`,
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      return { email, phone, password, firstName, token };
    } catch (error) {
      if (attempt >= 4 || !String(error).includes(" 409 ")) throw error;
    }
  }
}

export function openWallet(customer: Customer, currency = "UZS"): Promise<Wallet> {
  return call<Wallet>(`${BASE}/api/v1/wallets`, {
    method: "POST",
    token: customer.token,
    body: JSON.stringify({ currency }),
  });
}

/** Puts money on a wallet the only way money enters FinCore: a posting
 * from the external-funding account through ledger-service's internal
 * API (ADR-0002), as tests/e2e and scripts/dev-fund-wallet.sh do. */
export async function fund(wallet: Wallet, amountMinor: number): Promise<void> {
  const headers = { "X-Internal-Token": ledgerToken() };
  const funding = await call<{ id: string }>(
    `${LEDGER}/internal/v1/accounts/system?kind=EXTERNAL_FUNDING&currency=${wallet.currency}`,
    { headers },
  );
  await call(`${LEDGER}/internal/v1/postings`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      source_service: "browser-tests",
      source_id: `fund-${randomUUID()}`,
      type: "DEPOSIT",
      currency: wallet.currency,
      entries: [
        { account_id: funding.id, direction: "DEBIT", amount_minor: amountMinor },
        { account_id: wallet.id, direction: "CREDIT", amount_minor: amountMinor },
      ],
    }),
  });
}

export function balance(customer: Customer, wallet: Wallet): Promise<number> {
  return call<{ balance_minor: number }>(`${BASE}/api/v1/wallets/${wallet.id}`, {
    token: customer.token,
  }).then((body) => body.balance_minor);
}

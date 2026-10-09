import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import { clearAccessToken } from "../auth/tokenStore";
import { createQueryClient } from "../queryClient";

export interface RecordedRequest {
  method: string;
  path: string;
  search: string;
  headers: Record<string, string>;
  body: unknown;
}

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function problem(status: number, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ title, status, detail }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

export function noContent(): Response {
  return new Response(null, { status: 204 });
}

/** What the gateway's /api/v1/rates returns (units per US dollar). */
export const RATES = {
  result: "success",
  time_last_update_unix: 1_791_158_551,
  rates: { USD: 1, UZS: 12_000, EUR: 0.8, RUB: 80 },
};

// Requests every signed-in page makes regardless of what a test is
// about; a test can still override them.
const DEFAULT_ROUTES: Record<string, Handler> = {
  "GET /api/v1/rates": () => json(RATES),
  // The bell is on every signed-in page.
  "GET /api/v1/notifications": () => json({ unread_count: 0, items: [] }),
  "GET /api/v1/news": () => json({ unread_count: 0, items: [] }),
  // The Send page offers recent recipients when there are any.
  "GET /api/v1/transfers/recipients": () => json([]),
  // The admin console's menu counts what is waiting for staff.
  "GET /api/v1/admin/reviews": () => json([]),
  "GET /api/v1/admin/support/threads": () => json({ waiting_count: 0, unread_count: 0, items: [] }),
  // The console's first page: nothing has happened yet.
  "GET /api/v1/admin/stats": () =>
    json({ generated_at: "2026-10-08T10:00:00Z", awaiting_review: 0, currencies: [] }),
  "GET /api/v1/admin/users/stats": () => json({ total: 0, by_status: {}, days: [] }),
  // The home page offers saved payments and the latest operations.
  "GET /api/v1/templates": () => json([]),
  "GET /api/v1/transactions": () => json([]),
  // The chat launcher shows how many replies from staff are unread.
  "GET /api/v1/support/messages": () => json({ status: "OPEN", unread_count: 0, items: [] }),
  // The wallets page shows how many people are asking for money.
  "GET /api/v1/money-requests": () => json([]),
};

/**
 * Stubs global fetch with a route table keyed "METHOD /path" (query
 * string excluded). Unmatched requests fail the test loudly instead of
 * hanging. Every request is recorded for assertions.
 */
export function fakeApi(routes: Record<string, Handler>) {
  const requests: RecordedRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = Object.fromEntries(
      Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [
        k.toLowerCase(),
        v,
      ]),
    );
    const request: RecordedRequest = {
      method,
      path: url.pathname,
      search: url.search,
      headers,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    requests.push(request);
    const key = `${method} ${url.pathname}`;
    const handler =
      routes[key] ??
      DEFAULT_ROUTES[key] ??
      // Every money form reads the chosen card's daily limit: none set.
      (method === "GET" && url.pathname.startsWith("/api/v1/limits/")
        ? () => json(noLimit(url.pathname.split("/").pop() ?? ""))
        : // Admin tables name the customers in them; unknown unless a test says.
          method === "GET" && /^\/api\/v1\/admin\/users\/[0-9a-f-]{36}$/.test(url.pathname)
          ? () => problem(404, "User Not Found")
          : undefined);
    if (!handler) throw new Error(`unexpected request ${method} ${url.pathname}`);
    return handler(request);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { requests, fetchMock };
}

export const USER = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "ada@example.com",
  phone: "+998901112233",
  first_name: "Ada",
  last_name: "Lovelace",
  status: "ACTIVE",
  created_at: "2026-09-01T10:00:00Z",
  roles: ["USER"],
};

export const WALLET = {
  id: "22222222-2222-4222-8222-222222222222",
  card_number: "9955000000000006",
  currency: "UZS",
  status: "ACTIVE",
  created_at: "2026-09-01T10:00:00Z",
  balance_minor: 150_000,
  held_minor: 25_000,
  name: null as string | null,
  is_primary: true,
  blocked: false,
};

/** What /api/v1/limits/{wallet} answers for a card with no limit set. */
export function noLimit(walletId: string) {
  return {
    wallet_id: walletId,
    currency: "UZS",
    daily_limit_minor: null as number | null,
    spent_minor: 0,
    remaining_minor: null as number | null,
    window_hours: 24,
  };
}

/** Routes for a browser that already holds a valid refresh cookie. */
export function signedInRoutes(user = USER): Record<string, Handler> {
  return {
    "POST /api/v1/auth/refresh": () =>
      json({ access_token: "access-1", refresh_token: null, expires_in: 900 }),
    "GET /api/v1/users/me": () => json(user),
  };
}

export function renderApp(path: string) {
  clearAccessToken();
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

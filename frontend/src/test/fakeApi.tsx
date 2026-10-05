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
    const handler = routes[key] ?? DEFAULT_ROUTES[key];
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
};

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

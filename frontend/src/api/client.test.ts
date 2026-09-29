import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, json, problem } from "../test/fakeApi";
import {
  clearAccessToken,
  getAccessToken,
  onSessionEnded,
  setAccessToken,
} from "../auth/tokenStore";
import { ApiError, apiRequest } from "./client";

beforeEach(() => clearAccessToken());

describe("apiRequest", () => {
  it("sends the bearer token, query and Idempotency-Key", async () => {
    setAccessToken("token-a");
    const { requests } = fakeApi({ "POST /api/v1/transfers": () => json({ id: "t1" }, 201) });

    const result = await apiRequest("/api/v1/transfers", {
      method: "POST",
      body: { amount: "1.00" },
      query: { limit: 5, empty: "", missing: undefined },
      idempotencyKey: "key-1",
    });

    expect(result).toEqual({ id: "t1" });
    expect(requests[0]).toMatchObject({
      search: "?limit=5",
      body: { amount: "1.00" },
      headers: {
        authorization: "Bearer token-a",
        "idempotency-key": "key-1",
        "content-type": "application/json",
      },
    });
  });

  it("turns an RFC 7807 response into an ApiError", async () => {
    setAccessToken("token-a");
    fakeApi({
      "GET /api/v1/wallets": () => problem(422, "Currency Mismatch", "source wallet is USD"),
    });

    const error = await apiRequest("/api/v1/wallets").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      title: "Currency Mismatch",
      detail: "source wallet is USD",
    });
  });

  it("refreshes an expired access token once and replays the request", async () => {
    setAccessToken("expired");
    const { requests } = fakeApi({
      "GET /api/v1/wallets": (request) =>
        request.headers.authorization === "Bearer fresh"
          ? json([])
          : problem(401, "Invalid Token"),
      "POST /api/v1/auth/refresh": () => json({ access_token: "fresh", expires_in: 900 }),
    });

    await expect(apiRequest("/api/v1/wallets")).resolves.toEqual([]);

    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      "GET /api/v1/wallets",
      "POST /api/v1/auth/refresh",
      "GET /api/v1/wallets",
    ]);
    // ADR-0006: the refresh call opts into the cookie transport.
    expect(requests[1]?.headers["x-refresh-token-transport"]).toBe("cookie");
    expect(getAccessToken()).toBe("fresh");
  });

  it("shares one refresh between concurrent 401s", async () => {
    setAccessToken("expired");
    const { requests } = fakeApi({
      "GET /api/v1/wallets": (request) =>
        request.headers.authorization === "Bearer fresh" ? json([]) : problem(401, "Invalid"),
      "GET /api/v1/merchants": (request) =>
        request.headers.authorization === "Bearer fresh" ? json([]) : problem(401, "Invalid"),
      "POST /api/v1/auth/refresh": () => json({ access_token: "fresh", expires_in: 900 }),
    });

    await Promise.all([apiRequest("/api/v1/wallets"), apiRequest("/api/v1/merchants")]);

    expect(requests.filter((r) => r.path === "/api/v1/auth/refresh")).toHaveLength(1);
  });

  it("ends the session when the refresh cookie is no good either", async () => {
    setAccessToken("expired");
    const ended = vi.fn();
    const unsubscribe = onSessionEnded(ended);
    fakeApi({
      "GET /api/v1/wallets": () => problem(401, "Invalid Token"),
      "POST /api/v1/auth/refresh": () => problem(401, "Invalid Token"),
    });

    await expect(apiRequest("/api/v1/wallets")).rejects.toMatchObject({ status: 401 });

    expect(ended).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
    unsubscribe();
  });

  it("does not try to refresh for unauthenticated calls", async () => {
    const { requests } = fakeApi({
      "POST /api/v1/auth/login": () => problem(401, "Invalid Credentials"),
    });

    await expect(
      apiRequest("/api/v1/auth/login", { method: "POST", body: {}, authenticated: false }),
    ).rejects.toMatchObject({ title: "Invalid Credentials" });
    expect(requests).toHaveLength(1);
    expect(requests[0]?.headers.authorization).toBeUndefined();
  });
});

// Reference exchange rates, served by the gateway from a cached copy of
// a public provider (open.er-api.com). Not a FinCore service, so there is
// no contract schema to generate from: the shape is checked here instead.
import { apiRequest } from "./client";

export interface ExchangeRates {
  /** Units of each currency per one US dollar. */
  rates: Record<string, number>;
  updatedAt: Date | null;
}

interface ProviderResponse {
  result?: string;
  time_last_update_unix?: number;
  rates?: Record<string, unknown>;
}

export async function getExchangeRates(): Promise<ExchangeRates> {
  const data = await apiRequest<ProviderResponse>("/api/v1/rates", { authenticated: false });
  const rates: Record<string, number> = {};
  for (const [code, value] of Object.entries(data.rates ?? {})) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) rates[code] = value;
  }
  if (data.result !== "success" || rates.USD === undefined) {
    throw new Error("Exchange rates are unavailable right now.");
  }
  const updated = data.time_last_update_unix;
  return { rates, updatedAt: typeof updated === "number" ? new Date(updated * 1000) : null };
}

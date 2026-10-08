import { endSession, getAccessToken, refreshAccessToken } from "../auth/tokenStore";

/** An RFC 7807 problem response from any FinCore service. */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | undefined;

  constructor(status: number, title: string, detail?: string) {
    super(detail ? `${title}: ${detail}` : title);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = detail;
  }
}

type Query = Record<string, string | number | undefined | null>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  headers?: Record<string, string>;
  /** Money-moving POSTs (spec Section 9.1). Callers keep the same key
   * across retries of one user action, so a retry can't pay twice. */
  idempotencyKey?: string;
  /** Default true. Auth endpoints themselves send no bearer token. */
  authenticated?: boolean;
}

function buildUrl(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const problem = (await response.json()) as { title?: string; detail?: string };
    return new ApiError(response.status, problem.title ?? response.statusText, problem.detail);
  } catch {
    return new ApiError(response.status, response.statusText || "Request failed");
  }
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  const token = options.authenticated === false ? null : getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);

  // An expired access token is routine (15 min TTL): refresh once and
  // replay. Safe for POSTs too — the first attempt was rejected before
  // any handler ran, and money-moving calls carry an Idempotency-Key.
  if (response.status === 401 && options.authenticated !== false) {
    const refreshed = await refreshAccessToken();
    if (refreshed === "unavailable") {
      // The session may well be fine; only the server is unreachable.
      // Report that, and don't sign the user out over it.
      throw new ApiError(503, "Can't reach FinCore", "Check your connection and try again.");
    }
    if (refreshed === "ok") {
      response = await send(path, options);
    }
    if (response.status === 401) {
      endSession();
    }
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** A file the API serves as an attachment (a PDF receipt, a CSV
 * statement), with the name the server gave it. */
export interface Download {
  blob: Blob;
  filename: string;
}

/** Fetches a file with the customer's token - a plain link can't carry
 * one - going through the same refresh-and-replay as `apiRequest`. */
export async function apiDownload(path: string, fallbackName: string): Promise<Download> {
  let response = await send(path, { headers: { Accept: "*/*" } });
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed === "unavailable") {
      throw new ApiError(503, "Can't reach FinCore", "Check your connection and try again.");
    }
    if (refreshed === "ok") response = await send(path, { headers: { Accept: "*/*" } });
    if (response.status === 401) endSession();
  }
  if (!response.ok) throw await toApiError(response);
  const named = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  return { blob: await response.blob(), filename: named?.[1] ?? fallbackName };
}

/** Hands a fetched file to the browser's own "save" behaviour. */
export function saveDownload({ blob, filename }: Download): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // After the click has been handled; revoking at once can cancel it.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

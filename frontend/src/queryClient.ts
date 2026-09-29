import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A 4xx won't change on retry; only network/5xx errors are worth it.
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status < 500) && failureCount < 2,
        staleTime: 10_000,
      },
      // Never retry a mutation automatically: the user decides whether
      // to resubmit (with the same Idempotency-Key) after seeing the error.
      mutations: { retry: false },
    },
  });
}

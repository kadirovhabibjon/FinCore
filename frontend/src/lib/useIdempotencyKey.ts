import { useCallback, useState } from "react";

/**
 * One Idempotency-Key per user action (spec Section 9.1). The key stays
 * the same while the user retries a failed submit — so a request that
 * actually went through but whose response was lost is replayed, not
 * repeated — and is renewed only once the action succeeded or the form
 * input changed into a different request.
 */
export function useIdempotencyKey(): [string, () => void] {
  const [key, setKey] = useState(() => crypto.randomUUID());
  const renew = useCallback(() => setKey(crypto.randomUUID()), []);
  return [key, renew];
}

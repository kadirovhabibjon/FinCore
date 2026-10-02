/**
 * A random v4 UUID. `crypto.randomUUID()` only exists in secure contexts
 * (HTTPS or localhost), so opening the app by LAN address over plain
 * http — e.g. from a phone on the same Wi-Fi — would otherwise crash
 * every form that needs an Idempotency-Key. `crypto.getRandomValues` is
 * available everywhere and is just as random.
 */
export function randomUuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8]! & 0x3f) | 0x80; // RFC 4122 variant
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

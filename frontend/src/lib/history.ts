// How one operation of the history reads: shared by the History page
// and the home page's recent activity.
import type { Transaction } from "../api/endpoints";
import type { MessageKey } from "../i18n";

export function describe(item: Transaction): MessageKey {
  if (item.type === "PAYMENT") return "history.payment";
  if (item.type === "EXCHANGE") return "history.exchanged";
  return item.direction === "IN" ? "history.received" : "history.sent";
}

const NOT_MOVED = new Set(["FAILED", "EXPIRED", "CANCELLED"]);

/** "+" for money in, "−" for money out, nothing when none moved. */
export function sign(item: Transaction): string {
  // An exchange is the customer's own money changing currency: neither in nor out.
  if (NOT_MOVED.has(item.status) || item.direction === "SELF") return "";
  return item.direction === "IN" ? "+" : "−";
}

// A notification in the reader's language. The server writes the text
// in English and sends, next to it, the facts it was built from; in
// another language the same sentence is rebuilt here from those facts.
// English, announcements and anything older than the facts keep the
// server's own text.
import type { Notification } from "../api/endpoints";
import type { I18n, MessageKey } from "../i18n";
import { reasonText } from "./reasons";

type Facts = Record<string, unknown>;

function text(facts: Facts, name: string): string | undefined {
  const value = facts[name];
  return typeof value === "string" && value ? value : undefined;
}

/** Which template says it, given what is known. */
function bodyKey(type: string, facts: Facts): MessageKey | undefined {
  const named = text(facts, "counterparty") !== undefined;
  switch (type) {
    case "transfer.completed":
      return named ? "notif.transfer.completed.body" : "notif.transfer.completed.plain";
    case "transfer.failed":
      return "notif.transfer.failed.body";
    case "transfer.received":
      return named ? "notif.transfer.received.body" : "notif.transfer.received.plain";
    case "payment.completed":
      return named ? "notif.payment.completed.body" : "notif.payment.completed.plain";
    case "payment.received":
      return named ? "notif.payment.received.body" : "notif.payment.received.plain";
    case "payment.failed":
      return "notif.payment.failed.body";
    case "payment.refunded":
      return facts.partial === true ? "notif.payment.refunded.partial" : "notif.payment.refunded.body";
    case "money_request.created":
      return text(facts, "note") !== undefined
        ? "notif.money_request.created.note"
        : "notif.money_request.created.body";
    case "money_request.declined":
      return "notif.money_request.declined.body";
    case "exchange.completed":
      return "notif.exchange.completed.body";
    case "exchange.failed":
      return "notif.exchange.failed.body";
    default:
      return undefined;
  }
}

export function localize(item: Notification, i18n: I18n): { title: string; body: string } {
  const facts = item.params as Facts | null | undefined;
  const key = facts ? bodyKey(item.type, facts) : undefined;
  if (i18n.lang === "en" || !facts || !key) return { title: item.title, body: item.body };

  // Without a stated reason the server says "an internal error".
  const reason = text(facts, "reason") ?? "an internal error";
  const nobody = item.type === "money_request.declined" ? "notif.personAsked" : "notif.someone";
  return {
    title: i18n.maybe(`notif.${item.type}.title`) ?? item.title,
    body: i18n.t(key, {
      amount: text(facts, "amount") ?? "",
      received: text(facts, "received") ?? "",
      reference: text(facts, "reference") ?? "",
      note: text(facts, "note") ?? "",
      counterparty: text(facts, "counterparty") ?? i18n.t(nobody),
      reason: reasonText(reason, i18n),
    }),
  };
}

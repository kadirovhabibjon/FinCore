// The chat with FinCore's staff, shared by the widget and the bell.

/** Longest message the server takes. */
export const SUPPORT_MAX_CHARS = 2000;

const OPEN_EVENT = "fincore:open-support";

/** Asks the chat widget to open on the operator's side (the bell does,
 * when the customer taps "Support replied"). */
export function openSupportChat(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function onOpenSupportChat(handler: () => void): () => void {
  window.addEventListener(OPEN_EVENT, handler);
  return () => window.removeEventListener(OPEN_EVENT, handler);
}

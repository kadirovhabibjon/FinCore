import type { ChatMessage } from "../api/endpoints";

// Must stay within assistant-service's limits (max_history_messages,
// max_message_chars); older turns are dropped from what gets sent.
const MAX_SENT_MESSAGES = 20;
export const MAX_CHARS = 2000;

/** What gets sent: the latest turns, starting with a customer message,
 * ending with the new one. */
export function conversationToSend(history: ChatMessage[]): ChatMessage[] {
  const recent = history.slice(-MAX_SENT_MESSAGES);
  return recent[0]?.role === "assistant" ? recent.slice(1) : recent;
}

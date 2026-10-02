import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { MAX_CHARS, conversationToSend } from "../lib/chat";

const GREETING =
  "Hi! I can answer questions about your FinCore wallets, transfers, payments and account. " +
  "Assalomu alaykum! Savolingizni o'zbek, rus yoki ingliz tilida yozishingiz mumkin.";

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return error.detail ?? "Too many messages. Please wait a little.";
    if (error.status === 503) return error.detail ?? "The assistant is unavailable right now.";
    return error.detail ?? error.title;
  }
  return "Couldn't reach the assistant. Check your connection and try again.";
}

/** Customer support chat (ADR-0007), on every page of the customer site.
 * Replies are rendered as plain text, never as HTML. */
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<api.ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [history, pending, open]);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || pending) return;
    const next = [...history, { role: "user" as const, content: question }];
    setHistory(next);
    setDraft("");
    setError(null);
    setPending(true);
    try {
      const { reply } = await api.askAssistant(conversationToSend(next));
      setHistory([...next, { role: "assistant", content: reply }]);
    } catch (caught) {
      // Take the unanswered question back out, so the conversation keeps
      // alternating and the customer can resend it.
      setHistory(history);
      setDraft(question);
      setError(errorText(caught));
    } finally {
      setPending(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  if (!open) {
    return (
      <button type="button" className="chat-launcher" onClick={() => setOpen(true)}>
        Ask FinCore
      </button>
    );
  }

  return (
    <section className="chat-panel" aria-label="FinCore assistant">
      <header className="chat-header">
        <strong>FinCore assistant</strong>
        <button
          type="button"
          className="button button-small button-ghost"
          aria-label="Close chat"
          onClick={() => setOpen(false)}
        >
          ✕
        </button>
      </header>
      <div className="chat-log" role="log" aria-live="polite">
        <p className="chat-bubble chat-assistant">{GREETING}</p>
        {history.map((message, index) => (
          <p key={index} className={`chat-bubble chat-${message.role}`}>
            {message.content}
          </p>
        ))}
        {pending && <p className="chat-bubble chat-assistant chat-typing">Looking into it…</p>}
        <div ref={endRef} />
      </div>
      {error && (
        <div className="alert alert-error chat-error" role="alert">
          {error}
        </div>
      )}
      <form className="chat-form" onSubmit={send}>
        <textarea
          aria-label="Message"
          placeholder="Ask about your balance, a transfer…"
          rows={2}
          maxLength={MAX_CHARS}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="button" disabled={pending || !draft.trim()}>
          Send
        </button>
      </form>
      <p className="chat-note muted">AI answers from your account data. It can't move money.</p>
    </section>
  );
}

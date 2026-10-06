import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { MAX_CHARS, conversationToSend } from "../lib/chat";
import { useI18n, type I18n } from "../i18n";

/** The API's own explanation in English; in another language, the
 * plain reason for the two things that actually happen (too many
 * messages, no model to answer). */
function errorText(error: unknown, { t, lang }: I18n): string {
  if (error instanceof ApiError) {
    const own = lang === "en" ? error.detail : undefined;
    if (error.status === 429) return own ?? t("chat.tooMany");
    if (error.status === 503) return own ?? t("chat.unavailable");
    return error.detail ?? error.title;
  }
  return t("chat.unreachable");
}

/** Customer support chat (ADR-0007), on every page of the customer site.
 * Replies are rendered as plain text, never as HTML. */
export function ChatWidget() {
  const i18n = useI18n();
  const { t } = i18n;
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
      setError(errorText(caught, i18n));
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
        {t("chat.launch")}
      </button>
    );
  }

  return (
    <section className="chat-panel" aria-label={t("chat.title")}>
      <header className="chat-header">
        <strong>{t("chat.title")}</strong>
        <button
          type="button"
          className="button button-small button-ghost"
          aria-label={t("chat.close")}
          onClick={() => setOpen(false)}
        >
          ✕
        </button>
      </header>
      <div className="chat-log" role="log" aria-live="polite">
        <p className="chat-bubble chat-assistant">{t("chat.greeting")}</p>
        {history.map((message, index) => (
          <p key={index} className={`chat-bubble chat-${message.role}`}>
            {message.content}
          </p>
        ))}
        {pending && <p className="chat-bubble chat-assistant chat-typing">{t("chat.thinking")}</p>}
        <div ref={endRef} />
      </div>
      {error && (
        <div className="alert alert-error chat-error" role="alert">
          {error}
        </div>
      )}
      <form className="chat-form" onSubmit={send}>
        <textarea
          aria-label={t("chat.message")}
          placeholder={t("chat.placeholder")}
          rows={2}
          maxLength={MAX_CHARS}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="button" disabled={pending || !draft.trim()}>
          {t("chat.send")}
        </button>
      </form>
      <p className="chat-note muted">{t("chat.note")}</p>
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { MAX_CHARS, conversationToSend } from "../lib/chat";
import { useI18n, type I18n } from "../i18n";
import { onOpenSupportChat } from "../lib/support";
import { OperatorChat } from "./OperatorChat";

// How often to ask whether staff have replied while the chat is shut.
const CLOSED_POLL_MS = 30_000;

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

/** Customer support chat (ADR-0007), on every page of the customer site:
 * the AI assistant, and next to it the conversation with FinCore's
 * staff for what the assistant can't settle. Everything is rendered as
 * plain text, never as HTML. */
export function ChatWidget() {
  const i18n = useI18n();
  const { t } = i18n;
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"assistant" | "operator">("assistant");
  const [operatorDraft, setOperatorDraft] = useState("");
  // Replies from staff the customer hasn't opened, for the launcher's
  // badge. A failure is not worth showing: the bell tells them too.
  const support = useQuery({
    queryKey: ["support"],
    queryFn: api.getSupportConversation,
    refetchInterval: CLOSED_POLL_MS,
    retry: false,
  });
  const unreadReplies = support.data?.unread_count ?? 0;
  useEffect(
    () =>
      onOpenSupportChat(() => {
        setTab("operator");
        setOpen(true);
      }),
    [],
  );
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

  function toOperator() {
    // What the customer last asked (or was still typing), unless they
    // have already started writing to the operator.
    const lastQuestion =
      draft.trim() || [...history].reverse().find((message) => message.role === "user")?.content;
    if (!operatorDraft.trim() && lastQuestion) setOperatorDraft(lastQuestion);
    setTab("operator");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className="chat-launcher"
        onClick={() => {
          // Straight to what is new.
          if (unreadReplies > 0) setTab("operator");
          setOpen(true);
        }}
      >
        {t("chat.launch")}
        {unreadReplies > 0 && (
          <span className="chat-badge" aria-label={t("operator.unread", { count: unreadReplies })}>
            {unreadReplies > 9 ? "9+" : unreadReplies}
          </span>
        )}
      </button>
    );
  }

  return (
    <section
      className="chat-panel"
      aria-label={tab === "assistant" ? t("chat.title") : t("operator.title")}
    >
      <header className="chat-header">
        <div className="chat-tabs" role="group" aria-label={t("chat.tabs")}>
          <button
            type="button"
            aria-pressed={tab === "assistant"}
            onClick={() => setTab("assistant")}
          >
            {t("chat.tabAssistant")}
          </button>
          <button
            type="button"
            aria-pressed={tab === "operator"}
            onClick={() => setTab("operator")}
          >
            {t("chat.tabOperator")}
            {unreadReplies > 0 && tab !== "operator" && (
              <span className="chat-badge" aria-hidden="true">
                {unreadReplies > 9 ? "9+" : unreadReplies}
              </span>
            )}
          </button>
        </div>
        <button
          type="button"
          className="button button-small button-ghost"
          aria-label={t("chat.close")}
          onClick={() => setOpen(false)}
        >
          ✕
        </button>
      </header>
      {tab === "operator" ? (
        <OperatorChat draft={operatorDraft} onDraftChange={setOperatorDraft} />
      ) : (
        <>
          <div className="chat-log" role="log" aria-live="polite">
            <p className="chat-bubble chat-assistant">{t("chat.greeting")}</p>
            {history.map((message, index) => (
              <p key={index} className={`chat-bubble chat-${message.role}`}>
                {message.content}
              </p>
            ))}
            {pending && (
              <p className="chat-bubble chat-assistant chat-typing">{t("chat.thinking")}</p>
            )}
            <div ref={endRef} />
          </div>
          {error && (
            <div className="alert alert-error chat-error" role="alert">
              {error}
            </div>
          )}
          {/* Once something was asked: the way to a person, with the
              question carried over so it needn't be typed twice. */}
          {(history.length > 0 || error) && (
            <p className="chat-handoff muted small">
              {t("chat.noAnswer")}{" "}
              <button type="button" className="link-button" onClick={toOperator}>
                {t("chat.toOperator")}
              </button>
            </p>
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
        </>
      )}
    </section>
  );
}

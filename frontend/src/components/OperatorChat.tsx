import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { SUPPORT_MAX_CHARS } from "../lib/support";

const OPEN_POLL_MS = 8_000;

/** The customer's conversation with FinCore's staff, inside the chat
 * widget. Polls while it is on screen (nothing pushes to the browser);
 * looking at it marks the replies read. Messages are plain text. */
export function OperatorChat({
  draft,
  onDraftChange,
}: {
  draft: string;
  onDraftChange: (value: string) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const endRef = useRef<HTMLDivElement>(null);
  const conversation = useQuery({
    queryKey: ["support"],
    queryFn: api.getSupportConversation,
    refetchInterval: OPEN_POLL_MS,
    retry: false,
  });
  const markRead = useMutation({
    mutationFn: api.markSupportRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["support"] }),
  });
  const send = useMutation({
    mutationFn: (body: string) => api.writeToSupport(body),
    onSuccess: () => {
      onDraftChange("");
      return queryClient.invalidateQueries({ queryKey: ["support"] });
    },
  });

  const items = conversation.data?.items ?? [];
  const unread = conversation.data?.unread_count ?? 0;
  const { mutate: read, isPending: reading } = markRead;
  useEffect(() => {
    if (unread > 0 && !reading) read();
  }, [unread, reading, read]);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [items.length]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const body = draft.trim();
    if (!body || send.isPending) return;
    send.mutate(body);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const tooMany = send.error instanceof ApiError && send.error.status === 429;
  return (
    <>
      <div className="chat-log" role="log" aria-live="polite" aria-label={t("operator.title")}>
        <p className="chat-bubble chat-assistant">{t("operator.intro")}</p>
        {items.map((message) => (
          <p
            key={message.id}
            className={`chat-bubble chat-${message.sender === "CUSTOMER" ? "user" : "assistant"}`}
          >
            <span className="chat-sender">
              {message.sender === "CUSTOMER" ? t("operator.you") : t("operator.staff")}
            </span>
            {message.body}
          </p>
        ))}
        {conversation.data?.status === "RESOLVED" && (
          <p className="chat-system muted small">{t("operator.resolved")}</p>
        )}
        <div ref={endRef} />
      </div>
      {(conversation.isError || send.isError) && (
        <div className="alert alert-error chat-error" role="alert">
          {send.isError
            ? tooMany
              ? t("operator.tooMany")
              : t("operator.sendFailed")
            : t("operator.loadFailed")}
        </div>
      )}
      <form className="chat-form" onSubmit={submit}>
        <textarea
          aria-label={t("chat.message")}
          placeholder={t("operator.placeholder")}
          rows={2}
          maxLength={SUPPORT_MAX_CHARS}
          value={draft}
          onChange={(event) => {
            onDraftChange(event.target.value);
            if (send.isError) send.reset();
          }}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="button" disabled={send.isPending || !draft.trim()}>
          {t("chat.send")}
        </button>
      </form>
      <p className="chat-note muted">{t("operator.note")}</p>
    </>
  );
}

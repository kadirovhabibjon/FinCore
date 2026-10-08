import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../../components/ui";
import { CustomerContact, CustomerName } from "../../components/admin/Customer";
import { useI18n } from "../../i18n";
import { SUPPORT_MAX_CHARS } from "../../lib/support";

const INBOX_POLL_MS = 10_000;
const THREAD_POLL_MS = 5_000;

/** Customers' conversations with staff: an inbox and, beside it, the
 * conversation being answered (?user= in the URL, so it can be linked). */
export function AdminSupportPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const selected = params.get("user");
  // Resolved conversations are history: out of the way until asked for.
  const [showResolved, setShowResolved] = useState(false);
  const inbox = useQuery({
    queryKey: ["admin", "support", "inbox", showResolved ? "all" : "open"],
    queryFn: () => api.adminSupportInbox(showResolved ? undefined : "OPEN"),
    refetchInterval: INBOX_POLL_MS,
  });
  const listed = inbox.data?.items ?? [];

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("admin.support.title")}</h1>
          <p className="muted">
            {t("admin.support.intro")}{" "}
            {inbox.data
              ? inbox.data.waiting_count === 0
                ? t("admin.support.nobodyWaiting")
                : t("admin.support.waiting", { count: inbox.data.waiting_count })
              : ""}
          </p>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(event) => setShowResolved(event.target.checked)}
          />
          {t("admin.support.showResolved")}
        </label>
      </header>
      <ErrorAlert error={inbox.error} />
      {inbox.isPending ? (
        <Loading what={t("admin.support.loading")} />
      ) : listed.length === 0 && !selected ? (
        <Empty>
          {showResolved ? t("admin.support.nobodyWrote") : t("admin.support.noOpen")}
        </Empty>
      ) : (
        <div className="support-layout">
          <ul className="support-inbox" aria-label={t("admin.support.conversations")}>
            {listed.length === 0 && (
              <li className="muted small">{t("admin.support.noOpen")}</li>
            )}
            {listed.map((thread) => (
              <li key={thread.user_id}>
                <button
                  type="button"
                  className="support-thread"
                  aria-current={thread.user_id === selected}
                  onClick={() => setParams({ user: thread.user_id })}
                >
                  <span className="support-thread-head">
                    <strong>
                      <CustomerName userId={thread.user_id} />
                    </strong>
                    {thread.unread_count > 0 && (
                      <span className="chat-badge" aria-label={t("admin.support.unread", { count: thread.unread_count })}>
                        {thread.unread_count}
                      </span>
                    )}
                  </span>
                  <span className="muted small support-preview">
                    {thread.last_sender === "STAFF" ? t("admin.support.you") : ""}
                    {thread.last_body}
                  </span>
                  <span className="muted small">
                    <DateTime value={thread.last_message_at} />
                    {thread.status === "RESOLVED" && t("admin.support.resolvedMark")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? (
            <Conversation key={selected} userId={selected} />
          ) : (
            <Empty>{t("admin.support.choose")}</Empty>
          )}
        </div>
      )}
    </section>
  );
}

function Conversation({ userId }: { userId: string }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin", "support", "inbox"] });
    return queryClient.invalidateQueries({ queryKey: ["admin", "support", "thread", userId] });
  };
  const thread = useQuery({
    queryKey: ["admin", "support", "thread", userId],
    queryFn: () => api.adminSupportThread(userId),
    refetchInterval: THREAD_POLL_MS,
  });
  const act = useMutation({
    mutationFn: (action: "read" | "resolve" | "reopen") => api.adminSupportAct(userId, action),
    onSuccess: refresh,
  });
  const reply = useMutation({
    mutationFn: () => api.adminSupportReply(userId, draft.trim()),
    onSuccess: () => {
      setDraft("");
      return refresh();
    },
  });

  // Having it on screen is reading it.
  const unread = thread.data?.unread_count ?? 0;
  const { mutate: run, isPending: acting } = act;
  useEffect(() => {
    if (unread > 0 && !acting) run("read");
  }, [unread, acting, run]);
  const count = thread.data?.items.length ?? 0;
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [count]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (draft.trim()) reply.mutate();
  }

  if (thread.isPending) return <Loading what={t("admin.support.loadingOne")} />;
  if (thread.error) return <ErrorAlert error={thread.error} />;
  const resolved = thread.data.status === "RESOLVED";

  return (
    <div className="card support-conversation">
      <header className="support-conversation-head">
        <div>
          <strong>
            <CustomerName userId={userId} />
          </strong>{" "}
          <StatusBadge status={thread.data.status} />
          <div className="muted small">
            <CustomerContact userId={userId} />
          </div>
          <div className="small">
            <Link to={`/admin/users/${userId}`}>{t("admin.support.openCustomer")}</Link>
            {" · "}
            <Link to={`/admin/transactions?user_id=${userId}`}>
              {t("admin.users.transactions")}
            </Link>
          </div>
        </div>
        <button
          type="button"
          className="button button-small button-ghost"
          disabled={act.isPending}
          onClick={() => act.mutate(resolved ? "reopen" : "resolve")}
        >
          {resolved ? t("admin.support.reopen") : t("admin.support.resolve")}
        </button>
      </header>
      <div className="support-log" role="log" aria-label={t("admin.support.messages")}>
        {thread.data.items.map((message) => (
          <p
            key={message.id}
            className={`chat-bubble chat-${message.sender === "STAFF" ? "user" : "assistant"}`}
          >
            <span className="chat-sender">
              {message.sender === "STAFF" ? t("admin.support.staff") : t("admin.support.customer")} ·{" "}
              <DateTime value={message.created_at} />
            </span>
            {message.body}
          </p>
        ))}
        <div ref={endRef} />
      </div>
      <form className="support-reply" onSubmit={onSubmit}>
        <ErrorAlert error={reply.error ?? act.error} />
        <label>
          {t("admin.support.reply")}
          <textarea
            rows={3}
            maxLength={SUPPORT_MAX_CHARS}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t("admin.support.replyPlaceholder")}
          />
        </label>
        <div className="actions">
          <span className="muted small">{t("admin.support.plainText")}</span>
          <button type="submit" className="button" disabled={reply.isPending || !draft.trim()}>
            {reply.isPending ? t("admin.support.sending") : t("admin.support.send")}
          </button>
        </div>
      </form>
    </div>
  );
}

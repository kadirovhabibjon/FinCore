import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import * as api from "../../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../../components/ui";
import { CustomerContact, CustomerName } from "../../components/admin/Customer";
import { SUPPORT_MAX_CHARS } from "../../lib/support";

const INBOX_POLL_MS = 10_000;
const THREAD_POLL_MS = 5_000;

/** Customers' conversations with staff: an inbox and, beside it, the
 * conversation being answered (?user= in the URL, so it can be linked). */
export function AdminSupportPage() {
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
          <h1>Support</h1>
          <p className="muted">
            Messages customers wrote to an operator from the chat on the site.{" "}
            {inbox.data
              ? inbox.data.waiting_count === 0
                ? "Nobody is waiting for an answer."
                : `${inbox.data.waiting_count} waiting for an answer.`
              : ""}
          </p>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(event) => setShowResolved(event.target.checked)}
          />
          Show resolved
        </label>
      </header>
      <ErrorAlert error={inbox.error} />
      {inbox.isPending ? (
        <Loading what="Loading conversations" />
      ) : listed.length === 0 && !selected ? (
        <Empty>
          {showResolved ? "No customer has written yet." : "No open conversations."}
        </Empty>
      ) : (
        <div className="support-layout">
          <ul className="support-inbox" aria-label="Conversations">
            {listed.length === 0 && <li className="muted small">No open conversations.</li>}
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
                      <span className="chat-badge" aria-label={`${thread.unread_count} unread`}>
                        {thread.unread_count}
                      </span>
                    )}
                  </span>
                  <span className="muted small support-preview">
                    {thread.last_sender === "STAFF" ? "You: " : ""}
                    {thread.last_body}
                  </span>
                  <span className="muted small">
                    <DateTime value={thread.last_message_at} />
                    {thread.status === "RESOLVED" && " · resolved"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? (
            <Conversation key={selected} userId={selected} />
          ) : (
            <Empty>Choose a conversation to read and answer it.</Empty>
          )}
        </div>
      )}
    </section>
  );
}

function Conversation({ userId }: { userId: string }) {
  const queryClient = useQueryClient();
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

  if (thread.isPending) return <Loading what="Loading conversation" />;
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
            <Link to={`/admin/users?q=${userId}`}>Open in Users</Link>
            {" · "}
            <Link to={`/admin/transactions?user_id=${userId}`}>transactions</Link>
          </div>
        </div>
        <button
          type="button"
          className="button button-small button-ghost"
          disabled={act.isPending}
          onClick={() => act.mutate(resolved ? "reopen" : "resolve")}
        >
          {resolved ? "Reopen" : "Mark resolved"}
        </button>
      </header>
      <div className="support-log" role="log" aria-label="Messages">
        {thread.data.items.map((message) => (
          <p
            key={message.id}
            className={`chat-bubble chat-${message.sender === "STAFF" ? "user" : "assistant"}`}
          >
            <span className="chat-sender">
              {message.sender === "STAFF" ? "Staff" : "Customer"} ·{" "}
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
          Reply
          <textarea
            rows={3}
            maxLength={SUPPORT_MAX_CHARS}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="The customer sees this in the chat and in their notifications."
          />
        </label>
        <div className="actions">
          <span className="muted small">
            Plain text. Never ask for a password or a code.
          </span>
          <button type="submit" className="button" disabled={reply.isPending || !draft.trim()}>
            {reply.isPending ? "Sending…" : "Send reply"}
          </button>
        </div>
      </form>
    </div>
  );
}

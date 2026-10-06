import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime } from "./ui";

const POLL_INTERVAL_MS = 15_000;

const KIND: Record<string, { mark: string; className: string }> = {
  "transfer.received": { mark: "↓", className: "notification-in" },
  "transfer.completed": { mark: "↑", className: "notification-out" },
  "transfer.failed": { mark: "!", className: "notification-failed" },
  "payment.received": { mark: "↓", className: "notification-in" },
  "payment.completed": { mark: "↑", className: "notification-out" },
  "payment.failed": { mark: "!", className: "notification-failed" },
  "payment.refunded": { mark: "↩", className: "notification-in" },
  "exchange.completed": { mark: "⇄", className: "notification-out" },
  "exchange.failed": { mark: "!", className: "notification-failed" },
  "money_request.created": { mark: "?", className: "notification-request" },
  "money_request.declined": { mark: "✕", className: "notification-failed" },
  announcement: { mark: "i", className: "notification-announcement" },
};

type Tab = "activity" | "news";

/** The bell in the top bar, with one badge for two lists: the customer's
 * own activity (money received and sent) and banking news from public
 * feeds. Polls, since nothing pushes to the browser; looking at a list
 * marks it read. */
export function NotificationBell() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: api.listNotifications,
    refetchInterval: POLL_INTERVAL_MS,
    // The bell is decoration next to the page's real content: one failed
    // poll is not worth retrying ahead of the next one.
    retry: false,
  });
  const markRead = useMutation({
    mutationFn: api.markNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const unread = notifications.data?.unread_count ?? 0;
  const [tab, setTab] = useState<Tab>("activity");
  const news = useQuery({
    queryKey: ["news"],
    queryFn: () => api.listNews(),
    // News changes a few times a day at most.
    refetchInterval: 4 * POLL_INTERVAL_MS,
    retry: false,
  });
  const markNewsRead = useMutation({
    mutationFn: api.markNewsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["news"] }),
  });
  const unreadNews = news.data?.unread_count ?? 0;
  const total = unread + unreadNews;

  // Something new arrived while a page was open: its balances and
  // history are stale now.
  const seenUnread = useRef<number | null>(null);
  useEffect(() => {
    if (!notifications.data) return;
    if (seenUnread.current !== null && unread > seenUnread.current) {
      void queryClient.invalidateQueries({ queryKey: ["wallets"] });
      void queryClient.invalidateQueries({ queryKey: ["wallet"] });
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
    }
    seenUnread.current = unread;
  }, [notifications.data, unread, queryClient]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Unread items keep their highlight while the list stays on screen:
  // it is only replaced by the refetch that follows marking it read.
  function show(next: Tab) {
    setTab(next);
    if (next === "activity" && unread > 0) markRead.mutate();
    if (next === "news" && unreadNews > 0) markNewsRead.mutate();
  }

  function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    // Open on whichever list has something new; activity first.
    show(unread === 0 && unreadNews > 0 ? "news" : tab);
  }

  const items = notifications.data?.items ?? [];
  const newsItems = news.data?.items ?? [];
  return (
    <div className="bell" ref={container}>
      <button
        type="button"
        className="button button-ghost bell-button"
        aria-label={total > 0 ? `Notifications, ${total} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={toggle}
      >
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          focusable="false"
        >
          <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" />
          <path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        {total > 0 && (
          <span className="bell-badge" aria-hidden="true">
            {total > 9 ? "9+" : total}
          </span>
        )}
      </button>
      {open && (
        <div className="bell-panel" role="dialog" aria-label="Notifications">
          <div className="bell-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "activity"}
              onClick={() => show("activity")}
            >
              Activity
              {unread > 0 && <span className="bell-count">{unread}</span>}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "news"}
              onClick={() => show("news")}
            >
              News
              {unreadNews > 0 && <span className="bell-count">{unreadNews}</span>}
            </button>
            <Link
              to={tab === "news" ? "/news" : "/transactions"}
              className="bell-all"
              onClick={() => setOpen(false)}
            >
              {tab === "news" ? "All news" : "History"}
            </Link>
          </div>
          {tab === "activity" ? (
            notifications.isError && items.length === 0 ? (
              <p className="muted bell-empty">Couldn&apos;t load notifications.</p>
            ) : items.length === 0 ? (
              <p className="muted bell-empty">
                Nothing yet. Money you send and receive will show up here.
              </p>
            ) : (
              <ul className="bell-list">
                {items.map((item) => {
                  const kind = KIND[item.type] ?? { mark: "•", className: "" };
                  return (
                    <li key={item.id} className={item.read ? undefined : "unread"}>
                      <span className={`notification-mark ${kind.className}`} aria-hidden="true">
                        {kind.mark}
                      </span>
                      <span className="notification-text">
                        <strong>
                          {item.type.startsWith("money_request.") ? (
                            // Where it can be answered.
                            <Link to="/requests" onClick={() => setOpen(false)}>
                              {item.title}
                            </Link>
                          ) : (
                            item.title
                          )}
                        </strong>
                        <span>{item.body}</span>
                        <span className="muted small">
                          <DateTime value={item.created_at} />
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )
          ) : news.isError && newsItems.length === 0 ? (
            <p className="muted bell-empty">Couldn&apos;t load the news.</p>
          ) : newsItems.length === 0 ? (
            <p className="muted bell-empty">No banking news yet. Check back later.</p>
          ) : (
            <ul className="bell-list">
              {newsItems.map((item) => (
                <li key={item.id} className={item.unread ? "unread" : undefined}>
                  <Link
                    to={`/news/${item.id}`}
                    className="notification-text bell-news"
                    onClick={() => setOpen(false)}
                  >
                    <strong>{item.title}</strong>
                    <span className="muted small">
                      {item.source} · <DateTime value={item.published_at} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

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
};

/** The bell in the top bar: money received and sent, newest first, with
 * a badge for what hasn't been seen yet. Polls, since nothing pushes to
 * the browser; opening it marks everything read. */
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

  function toggle() {
    const opening = !open;
    setOpen(opening);
    // Unread items keep their highlight while the panel stays open: the
    // list on screen is only replaced by the refetch after this.
    if (opening && unread > 0) markRead.mutate();
  }

  const items = notifications.data?.items ?? [];
  return (
    <div className="bell" ref={container}>
      <button
        type="button"
        className="button button-ghost bell-button"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
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
        {unread > 0 && (
          <span className="bell-badge" aria-hidden="true">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="bell-panel" role="dialog" aria-label="Notifications">
          <div className="bell-head">
            <strong>Notifications</strong>
            <Link to="/transactions" onClick={() => setOpen(false)}>
              History
            </Link>
          </div>
          {notifications.isError && items.length === 0 ? (
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
                      <strong>{item.title}</strong>
                      <span>{item.body}</span>
                      <span className="muted small">
                        <DateTime value={item.created_at} />
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

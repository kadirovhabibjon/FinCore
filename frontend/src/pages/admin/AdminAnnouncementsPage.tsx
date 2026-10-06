import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { DateTime, Empty, ErrorAlert, Loading, Notice } from "../../components/ui";

const TITLE_MAX = 120;
const BODY_MAX = 1000;

export function AdminAnnouncementsPage() {
  const { user } = useAuth();
  const isAdmin = hasAnyRole(user, "ADMIN");
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "announcements"] });

  const announcements = useQuery({
    queryKey: ["admin", "announcements"],
    queryFn: api.adminListAnnouncements,
  });
  const publish = useMutation({
    mutationFn: api.adminPublishAnnouncement,
    onSuccess: () => {
      setTitle("");
      setBody("");
      return refresh();
    },
  });
  const withdraw = useMutation({
    mutationFn: api.adminWithdrawAnnouncement,
    onSuccess: refresh,
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    publish.mutate({ title: title.trim(), body: body.trim() });
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Announcements</h1>
          <p className="muted">
            A message to every customer at once: it appears in each customer&apos;s notifications
            bell.{" "}
            {isAdmin
              ? "Published immediately, as plain text."
              : "Publishing and withdrawing need the ADMIN role."}
          </p>
        </div>
      </header>
      {isAdmin && (
        <form className="card form" onSubmit={onSubmit}>
          {publish.isSuccess && <Notice>Published to every customer.</Notice>}
          <ErrorAlert error={publish.error} />
          <label>
            Title
            <input
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                if (!publish.isIdle) publish.reset();
              }}
              maxLength={TITLE_MAX}
              required
            />
          </label>
          <label>
            Message
            <textarea
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
                if (!publish.isIdle) publish.reset();
              }}
              rows={4}
              maxLength={BODY_MAX}
              required
            />
          </label>
          <div className="actions">
            <span className="muted small">
              {body.length} / {BODY_MAX}
            </span>
            <button
              type="submit"
              className="button"
              disabled={publish.isPending || !title.trim() || !body.trim()}
            >
              {publish.isPending ? "Publishing…" : "Publish to all customers"}
            </button>
          </div>
        </form>
      )}
      <h2>Published</h2>
      <ErrorAlert error={announcements.error ?? withdraw.error} />
      {announcements.isPending ? (
        <Loading what="Loading announcements" />
      ) : announcements.data?.length === 0 ? (
        <Empty>No announcements yet.</Empty>
      ) : (
        <ul className="list">
          {announcements.data?.map((item) => (
            <li key={item.id} className="card">
              <div className="list-row">
                <div>
                  <strong>{item.title}</strong>
                  <div className="announcement-body">{item.body}</div>
                  <div className="muted small">
                    <DateTime value={item.created_at} />
                  </div>
                </div>
                {isAdmin && (
                  <button
                    type="button"
                    className="button button-small button-danger"
                    disabled={withdraw.isPending}
                    onClick={() => withdraw.mutate(item.id)}
                  >
                    Withdraw
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

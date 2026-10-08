import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { ConfirmButton } from "../../components/admin/ConfirmButton";
import { useI18n } from "../../i18n";
import { DateTime, Empty, ErrorAlert, Loading, Notice } from "../../components/ui";

const TITLE_MAX = 120;
const BODY_MAX = 1000;

export function AdminAnnouncementsPage() {
  const { user } = useAuth();
  const { t } = useI18n();
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
          <h1>{t("admin.ann.title")}</h1>
          <p className="muted">
            {t("admin.ann.intro")}{" "}
            {isAdmin ? t("admin.ann.adminNote") : t("admin.ann.supportNote")}
          </p>
        </div>
      </header>
      {isAdmin && (
        <form className="card form" onSubmit={onSubmit}>
          {publish.isSuccess && <Notice>{t("admin.ann.published")}</Notice>}
          <ErrorAlert error={publish.error} />
          <label>
            {t("admin.ann.fieldTitle")}
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
            {t("admin.ann.fieldMessage")}
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
              {publish.isPending ? t("admin.ann.publishing") : t("admin.ann.publish")}
            </button>
          </div>
        </form>
      )}
      <h2>{t("admin.ann.list")}</h2>
      <ErrorAlert error={announcements.error ?? withdraw.error} />
      {announcements.isPending ? (
        <Loading what={t("admin.ann.loading")} />
      ) : announcements.data?.length === 0 ? (
        <Empty>{t("admin.ann.empty")}</Empty>
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
                  <ConfirmButton
                    confirm={t("admin.ann.confirmWithdraw")}
                    className="button button-small button-danger"
                    disabled={withdraw.isPending}
                    onConfirm={() => withdraw.mutate(item.id)}
                  >
                    {t("admin.ann.withdraw")}
                  </ConfirmButton>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

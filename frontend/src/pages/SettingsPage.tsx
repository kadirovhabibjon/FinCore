import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { EditProfileForm } from "../components/EditProfileForm";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../components/ui";
import { ThemeChoice } from "../components/ThemeSwitch";
import { useI18n } from "../i18n";

export function SettingsPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.listSessions });
  const revoke = useMutation({
    mutationFn: api.revokeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  if (!user) return null;

  return (
    <section className="page">
      <h1>{t("settings.title")}</h1>
      <dl className="card details">
        <dt>{t("settings.name")}</dt>
        <dd>
          {user.first_name} {user.last_name}
        </dd>
        <dt>{t("common.email")}</dt>
        <dd>{user.email}</dd>
        <dt>{t("settings.phone")}</dt>
        <dd>{user.phone}</dd>
        <dt>{t("settings.status")}</dt>
        <dd>
          <StatusBadge status={user.status} />
        </dd>
        <dt>{t("settings.roles")}</dt>
        <dd>{user.roles.join(", ")}</dd>
        <dt>{t("settings.userId")}</dt>
        <dd>
          <code>{user.id}</code>
        </dd>
      </dl>

      <h2>{t("settings.password")}</h2>
      <ChangePasswordForm />

      <h2>{t("settings.details")}</h2>
      <EditProfileForm user={user} />

      <h2>{t("theme.title")}</h2>
      <ThemeChoice />

      <h2>{t("settings.sessions")}</h2>
      <p className="muted">{t("settings.sessionsIntro")}</p>
      <ErrorAlert error={sessions.error ?? revoke.error} />
      {sessions.isPending ? (
        <Loading what={t("settings.loadingSessions")} />
      ) : sessions.data?.length === 0 ? (
        <Empty>{t("settings.noSessions")}</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("settings.device")}</th>
              <th>{t("settings.ip")}</th>
              <th>{t("settings.signedIn")}</th>
              <th>{t("settings.lastActive")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.data?.map((session) => (
              <tr key={session.id}>
                <td data-label={t("settings.device")}>
                  {session.user_agent ?? t("settings.unknownDevice")}
                  {session.current && (
                    <span className="badge badge-good">{t("settings.thisDevice")}</span>
                  )}
                </td>
                <td data-label={t("settings.ip")}>{session.ip_address ?? "—"}</td>
                <td data-label={t("settings.signedIn")}>
                  <DateTime value={session.created_at} />
                </td>
                <td data-label={t("settings.lastActive")}>
                  <DateTime value={session.last_used_at} />
                </td>
                <td className="num" data-label="">
                  {!session.current && (
                    <button
                      type="button"
                      className="button button-small button-ghost"
                      disabled={revoke.isPending}
                      onClick={() => revoke.mutate(session.id)}
                    >
                      {t("common.signOut")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

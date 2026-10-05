import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../components/ui";

export function SettingsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.listSessions });
  const revoke = useMutation({
    mutationFn: api.revokeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  if (!user) return null;

  return (
    <section className="page">
      <h1>Account</h1>
      <dl className="card details">
        <dt>Name</dt>
        <dd>
          {user.first_name} {user.last_name}
        </dd>
        <dt>Email</dt>
        <dd>{user.email}</dd>
        <dt>Phone</dt>
        <dd>{user.phone}</dd>
        <dt>Status</dt>
        <dd>
          <StatusBadge status={user.status} />
        </dd>
        <dt>Roles</dt>
        <dd>{user.roles.join(", ")}</dd>
        <dt>User id</dt>
        <dd>
          <code>{user.id}</code>
        </dd>
      </dl>

      <h2>Password</h2>
      <ChangePasswordForm />

      <h2>Active sessions</h2>
      <p className="muted">
        Every device signed in to your account. Signing one out ends it at its next token refresh —
        within 15 minutes. A device left unused for 15 minutes is signed out automatically.
      </p>
      <ErrorAlert error={sessions.error ?? revoke.error} />
      {sessions.isPending ? (
        <Loading what="Loading sessions" />
      ) : sessions.data?.length === 0 ? (
        <Empty>No active sessions.</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Device</th>
              <th>IP address</th>
              <th>Signed in</th>
              <th>Last active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.data?.map((session) => (
              <tr key={session.id}>
                <td data-label="Device">
                  {session.user_agent ?? "Unknown device"}
                  {session.current && <span className="badge badge-good">This device</span>}
                </td>
                <td data-label="IP address">{session.ip_address ?? "—"}</td>
                <td data-label="Signed in">
                  <DateTime value={session.created_at} />
                </td>
                <td data-label="Last active">
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
                      Sign out
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

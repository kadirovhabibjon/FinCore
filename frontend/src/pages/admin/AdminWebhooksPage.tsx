import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { ConfirmButton } from "../../components/admin/ConfirmButton";
import { CustomerLink } from "../../components/admin/Customer";
import { DeliveriesTable } from "../../components/DeliveriesTable";
import { Empty, ErrorAlert, Loading, Pager, ShortId, StatusBadge } from "../../components/ui";

const PAGE_SIZE = 50;

export function AdminWebhooksPage() {
  const { user } = useAuth();
  const isAdmin = hasAnyRole(user, "ADMIN");
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [openEndpoint, setOpenEndpoint] = useState<string | null>(null);

  const endpoints = useQuery({
    queryKey: ["admin", "webhooks", status, offset],
    queryFn: () => api.adminListWebhookEndpoints(status || undefined, { limit: PAGE_SIZE, offset }),
  });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.adminSetWebhookEndpointEnabled(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "webhooks"] }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Webhook endpoints</h1>
          <p className="muted">
            Every merchant&apos;s endpoints. Disabling one stops deliveries until it is enabled
            again; its owner can re-enable it too.
          </p>
        </div>
        <select
          aria-label="Endpoint status"
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
        >
          <option value="">Any status</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="DISABLED">DISABLED</option>
        </select>
      </header>
      <ErrorAlert error={endpoints.error ?? toggle.error} />
      {endpoints.isPending ? (
        <Loading what="Loading endpoints" />
      ) : endpoints.data?.length === 0 && offset === 0 ? (
        <Empty>No endpoints match.</Empty>
      ) : (
        <>
          <ul className="list">
            {endpoints.data?.map((endpoint) => (
              <li key={endpoint.id} className="card">
                <div className="list-row">
                  <div>
                    <code>{endpoint.url}</code>
                    <div className="muted small">
                      merchant <ShortId id={endpoint.merchant_id} /> · owner{" "}
                      <CustomerLink userId={endpoint.owner_user_id} /> ·{" "}
                      {endpoint.consecutive_failures}{" "}
                      consecutive failures
                    </div>
                  </div>
                  <div className="actions">
                    <StatusBadge status={endpoint.status} />
                    {isAdmin &&
                      (endpoint.status === "ACTIVE" ? (
                        // The merchant stops hearing about their payments.
                        <ConfirmButton
                          confirm="Confirm disable"
                          className="button button-small button-danger"
                          disabled={toggle.isPending}
                          onConfirm={() => toggle.mutate({ id: endpoint.id, enabled: false })}
                        >
                          Disable
                        </ConfirmButton>
                      ) : (
                        <button
                          type="button"
                          className="button button-small"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: endpoint.id, enabled: true })}
                        >
                          Enable
                        </button>
                      ))}
                    <button
                      type="button"
                      className="button button-small button-ghost"
                      onClick={() =>
                        setOpenEndpoint(openEndpoint === endpoint.id ? null : endpoint.id)
                      }
                    >
                      {openEndpoint === endpoint.id ? "Hide deliveries" : "Deliveries"}
                    </button>
                  </div>
                </div>
                {openEndpoint === endpoint.id && <AdminDeliveries endpointId={endpoint.id} />}
              </li>
            ))}
          </ul>
          <Pager
            offset={offset}
            limit={PAGE_SIZE}
            count={endpoints.data?.length ?? 0}
            onChange={setOffset}
          />
        </>
      )}
    </section>
  );
}

function AdminDeliveries({ endpointId }: { endpointId: string }) {
  const deliveries = useQuery({
    queryKey: ["admin", "webhooks", endpointId, "deliveries"],
    queryFn: () => api.adminListWebhookDeliveries(endpointId, { limit: 50, offset: 0 }),
  });
  if (deliveries.isPending) return <Loading what="Loading deliveries" />;
  if (deliveries.error) return <ErrorAlert error={deliveries.error} />;
  return <DeliveriesTable deliveries={deliveries.data} />;
}

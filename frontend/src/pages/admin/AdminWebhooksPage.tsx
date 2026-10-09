import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { ConfirmButton } from "../../components/ConfirmButton";
import { CustomerLink } from "../../components/admin/Customer";
import { useI18n } from "../../i18n";
import { DeliveriesTable } from "../../components/DeliveriesTable";
import { Empty, ErrorAlert, Loading, Pager, ShortId, StatusBadge } from "../../components/ui";

const PAGE_SIZE = 50;

export function AdminWebhooksPage() {
  const { user } = useAuth();
  const { t, tr, maybe } = useI18n();
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
          <h1>{t("admin.webhooks.title")}</h1>
          <p className="muted">{t("admin.webhooks.subtitle")}</p>
        </div>
        <select
          aria-label={t("admin.webhooks.status")}
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
        >
          <option value="">{t("admin.tx.anyStatus")}</option>
          <option value="ACTIVE">{maybe("status.ACTIVE") ?? "ACTIVE"}</option>
          <option value="DISABLED">{maybe("status.DISABLED") ?? "DISABLED"}</option>
        </select>
      </header>
      <ErrorAlert error={endpoints.error ?? toggle.error} />
      {endpoints.isPending ? (
        <Loading what={t("admin.webhooks.loading")} />
      ) : endpoints.data?.length === 0 && offset === 0 ? (
        <Empty>{t("admin.webhooks.empty")}</Empty>
      ) : (
        <>
          <ul className="list">
            {endpoints.data?.map((endpoint) => (
              <li key={endpoint.id} className="card">
                <div className="list-row">
                  <div>
                    <code>{endpoint.url}</code>
                    <div className="muted small">
                      {tr("admin.webhooks.meta", {
                        merchant: <ShortId id={endpoint.merchant_id} />,
                        owner: <CustomerLink userId={endpoint.owner_user_id} />,
                        failures: endpoint.consecutive_failures,
                      })}
                    </div>
                  </div>
                  <div className="actions">
                    <StatusBadge status={endpoint.status} />
                    {isAdmin &&
                      (endpoint.status === "ACTIVE" ? (
                        // The merchant stops hearing about their payments.
                        <ConfirmButton
                          confirm={t("admin.webhooks.confirmDisable")}
                          className="button button-small button-danger"
                          disabled={toggle.isPending}
                          onConfirm={() => toggle.mutate({ id: endpoint.id, enabled: false })}
                        >
                          {t("admin.webhooks.disable")}
                        </ConfirmButton>
                      ) : (
                        <button
                          type="button"
                          className="button button-small"
                          disabled={toggle.isPending}
                          onClick={() => toggle.mutate({ id: endpoint.id, enabled: true })}
                        >
                          {t("admin.webhooks.enable")}
                        </button>
                      ))}
                    <button
                      type="button"
                      className="button button-small button-ghost"
                      onClick={() =>
                        setOpenEndpoint(openEndpoint === endpoint.id ? null : endpoint.id)
                      }
                    >
                      {openEndpoint === endpoint.id
                        ? t("admin.webhooks.hideDeliveries")
                        : t("admin.webhooks.deliveries")}
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
  const { t } = useI18n();
  const deliveries = useQuery({
    queryKey: ["admin", "webhooks", endpointId, "deliveries"],
    queryFn: () => api.adminListWebhookDeliveries(endpointId, { limit: 50, offset: 0 }),
  });
  if (deliveries.isPending) return <Loading what={t("admin.webhooks.loadingDeliveries")} />;
  if (deliveries.error) return <ErrorAlert error={deliveries.error} />;
  return <DeliveriesTable deliveries={deliveries.data} />;
}

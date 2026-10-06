import type { WebhookDelivery } from "../api/endpoints";
import { DateTime, Empty, StatusBadge } from "./ui";
import { useI18n } from "../i18n";

export function DeliveriesTable({ deliveries }: { deliveries: WebhookDelivery[] }) {
  const { t } = useI18n();
  if (deliveries.length === 0) return <Empty>{t("deliveries.empty")}</Empty>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>{t("history.when")}</th>
          <th>{t("deliveries.event")}</th>
          <th>{t("history.status")}</th>
          <th>{t("deliveries.attempts")}</th>
        </tr>
      </thead>
      <tbody>
        {deliveries.map((delivery) => (
          <tr key={delivery.id}>
            <td data-label={t("history.when")}>
              <DateTime value={delivery.created_at} />
            </td>
            <td data-label={t("deliveries.event")}>
              {delivery.event_type}
              {delivery.last_error && <div className="muted small">{delivery.last_error}</div>}
            </td>
            <td data-label={t("history.status")}>
              <StatusBadge status={delivery.status} />
            </td>
            <td data-label={t("deliveries.attempts")}>
              <details>
                <summary>{delivery.attempts}</summary>
                <ol className="attempts">
                  {(delivery.attempt_history ?? []).map((attempt) => (
                    <li key={attempt.id}>
                      #{attempt.attempt_number} · {attempt.status_code ?? t("deliveries.noResponse")}
                      {attempt.latency_ms !== null && ` · ${attempt.latency_ms} ms`}
                      {attempt.error && ` · ${attempt.error}`}
                    </li>
                  ))}
                </ol>
              </details>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

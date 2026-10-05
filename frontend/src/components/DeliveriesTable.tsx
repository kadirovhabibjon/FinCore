import type { WebhookDelivery } from "../api/endpoints";
import { DateTime, Empty, StatusBadge } from "./ui";

export function DeliveriesTable({ deliveries }: { deliveries: WebhookDelivery[] }) {
  if (deliveries.length === 0) return <Empty>No deliveries yet.</Empty>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>When</th>
          <th>Event</th>
          <th>Status</th>
          <th>Attempts</th>
        </tr>
      </thead>
      <tbody>
        {deliveries.map((delivery) => (
          <tr key={delivery.id}>
            <td data-label="When">
              <DateTime value={delivery.created_at} />
            </td>
            <td data-label="Event">
              {delivery.event_type}
              {delivery.last_error && <div className="muted small">{delivery.last_error}</div>}
            </td>
            <td data-label="Status">
              <StatusBadge status={delivery.status} />
            </td>
            <td data-label="Attempts">
              <details>
                <summary>{delivery.attempts}</summary>
                <ol className="attempts">
                  {(delivery.attempt_history ?? []).map((attempt) => (
                    <li key={attempt.id}>
                      #{attempt.attempt_number} · {attempt.status_code ?? "no response"}
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

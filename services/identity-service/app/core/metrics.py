from prometheus_client import Gauge

# spec Section 24's "outbox backlog (unpublished events)" — same metric
# name as payment-service, told apart by the `service` label Prometheus
# attaches per scrape target.
OUTBOX_BACKLOG = Gauge("fincore_outbox_backlog", "Unpublished outbox_events rows.")

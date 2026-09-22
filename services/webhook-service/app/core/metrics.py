from fincore_common import Counter

# spec Section 24's "DLT message count," this service's own equivalent:
# webhook-service has no DLT topic (app/services/delivery.py retries off
# `webhook_deliveries.next_attempt_at` instead of Kafka), so a delivery
# reaching terminal FAILED — attempts exhausted, or its endpoint was
# disabled mid-flight — is the thing worth the same visibility.
DELIVERIES_TERMINALLY_FAILED_TOTAL = Counter(
    "fincore_deliveries_terminally_failed_total",
    "Webhook deliveries that reached terminal FAILED status.",
)

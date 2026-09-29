from fincore_common import Counter
from prometheus_client import Gauge

# spec Section 24's "fraud blocks" — broadened to every decision, not
# just BLOCK, since ALLOW/REVIEW counts are what a BLOCK rate needs as
# its denominator. Recorded here, at the point the decision is actually
# made, rather than re-derived from payment-service's own outcome —
# payment-service only ever calls this once per operation (spec Section
# 9.2's idempotency), so there's no double-counting risk either way.
FRAUD_CHECKS_TOTAL = Counter(
    "fincore_fraud_checks_total",
    "Total fraud risk checks scored, by decision.",
    ["decision"],
)

# spec Section 24's "outbox backlog (unpublished events)", as in
# payment- and identity-service.
OUTBOX_BACKLOG = Gauge("fincore_outbox_backlog", "Unpublished outbox_events rows.")

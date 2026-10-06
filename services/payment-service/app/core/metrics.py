from fincore_common import Counter, Gauge

# spec Section 24: "payment count," "failed payment count," "transfer
# count" — one Counter per aggregate, labeled by terminal status rather
# than split into separate "total" and "failed" series, so a failure
# rate is one query (`payments_total{status="FAILED"} /
# sum(payments_total)`) instead of two metrics that can drift apart.
TRANSFERS_TOTAL = Counter(
    "fincore_transfers_total", "Total transfers reaching a terminal status.", ["status"]
)
EXCHANGES_TOTAL = Counter(
    "fincore_exchanges_total", "Total currency exchanges reaching a terminal status.", ["status"]
)
PAYMENTS_TOTAL = Counter(
    "fincore_payments_total", "Total payments reaching a terminal status.", ["status"]
)

# spec Section 24: "outbox backlog (unpublished events)" — set by the
# outbox relay loop (app/main.py) after each pass to the *true* count
# of still-unpublished rows (app/repositories/outbox_repository.py's
# count_unpublished), not the size of the one batch just processed.
OUTBOX_BACKLOG = Gauge("fincore_outbox_backlog", "Unpublished outbox_events rows.")

# spec Section 24: "transfers stuck in PROCESSING" — broadened to every
# aggregate type the recovery worker covers (spec Section 10.1's
# transfers, payments and refunds all share the same "unknown ledger
# outcome" failure mode), set after each recovery pass to how many were
# found stuck at that check, regardless of whether this pass's retry
# resolved them.
STUCK_PROCESSING = Gauge(
    "fincore_stuck_processing",
    "Operations found stuck in PROCESSING on the most recent recovery pass.",
    ["operation_type"],
)

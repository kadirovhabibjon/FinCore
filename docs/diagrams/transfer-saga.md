# Transfer Saga — Sequence Diagram

This diagram is the visual form of Section 10.1 of [spec.md](../spec.md),
orchestrated by `payment-service`. It shows the happy path plus every
failure branch the saga must handle: fraud `BLOCK`, fraud `REVIEW`, and the
ledger call timing out (unknown outcome).

See [ADR-0003](../adr/0003-sync-vs-async-communication.md) for why the
`ledger-service` and `fraud-service` calls are synchronous, and
[ADR-0002](../adr/0002-ledger-model.md) for what a "posting" is.

## Happy path + failure branches

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant GW as Gateway
    participant PAY as payment-service
    participant FRAUD as fraud-service
    participant LEDGER as ledger-service
    participant OUTBOX as payment_db outbox
    participant KAFKA as Kafka

    Client->>GW: POST /api/v1/transfers (JWT, Idempotency-Key)
    GW->>PAY: forward (correlation_id attached)

    PAY->>PAY: verify JWT, authorize (user owns source wallet)
    PAY->>PAY: validate request (amount > 0, precision, same currency, source != destination)

    PAY->>PAY: idempotency check (insert IN_PROGRESS)
    Note over PAY: same key + IN_PROGRESS -> 409<br/>same key + different fingerprint -> 422<br/>same key + COMPLETED -> return stored response

    PAY->>PAY: create Transfer (PENDING) [local tx]

    PAY->>FRAUD: POST /internal/v1/risk-checks (timeout: low hundreds of ms)

    alt fraud: BLOCK
        FRAUD-->>PAY: BLOCK
        PAY->>PAY: Transfer -> FAILED [local tx]
        PAY->>OUTBOX: insert transfer.failed (same tx)
    else fraud: REVIEW
        FRAUD-->>PAY: REVIEW
        PAY->>PAY: Transfer stays PENDING [local tx]
        PAY->>OUTBOX: insert fraud.review_required (same tx)
        Note over PAY: waits for SUPPORT/ADMIN decision (not shown)
    else fraud: timeout / unavailable
        FRAUD--xPAY: timeout
        PAY->>PAY: apply fail-open/fail-closed policy (ADR-0003, spec Section 12)
        Note over PAY: amount <= low-risk limit -> ALLOW (flagged)<br/>amount > low-risk limit -> REVIEW
    else fraud: ALLOW
        FRAUD-->>PAY: ALLOW
        PAY->>PAY: Transfer PENDING -> PROCESSING [local tx]

        PAY->>LEDGER: POST /internal/v1/postings (source_id = transfer.id, timeout: a few seconds)

        alt ledger: success
            LEDGER->>LEDGER: lock accounts (ascending id order) FOR UPDATE
            LEDGER->>LEDGER: check wallet status + available balance (after lock)
            LEDGER->>LEDGER: insert posting + entries, update balances [one local tx]
            LEDGER->>LEDGER: insert outbox event ledger.posting.completed (same tx)
            LEDGER-->>PAY: 201 posting created
            PAY->>PAY: Transfer -> COMPLETED [local tx]
            PAY->>OUTBOX: insert transfer.completed (same tx)
            PAY->>PAY: store idempotent response (COMPLETED)
        else ledger: business rejection (e.g. insufficient funds)
            LEDGER-->>PAY: 4xx business rejection
            PAY->>PAY: Transfer -> FAILED [local tx]
            PAY->>OUTBOX: insert transfer.failed (same tx)
        else ledger: timeout / 5xx
            LEDGER--xPAY: timeout / 5xx
            Note over PAY: outcome UNKNOWN - do NOT mark FAILED.<br/>Transfer stays PROCESSING.<br/>Recovery worker retries same source_id<br/>or queries GET /internal/v1/postings/{source_id}.
        end
    end

    PAY-->>GW: response (per branch above)
    GW-->>Client: response

    OUTBOX->>KAFKA: outbox relay publishes unpublished events
    KAFKA-->>KAFKA: consumer groups: notification-service, webhook-service,<br/>audit-service each read independently
```

## Why each failure branch behaves the way it does

| Branch | Terminal state? | Reasoning |
|---|---|---|
| Fraud `BLOCK` | Yes — `FAILED` | A block is a definitive business decision, safe to finalize immediately. |
| Fraud `REVIEW` | No — stays `PENDING` | A human must decide; the saga cannot guess, so it parks rather than fails or succeeds. |
| Fraud unavailable/timeout | Depends on policy | The failure policy (ADR-0003 / spec Section 12) substitutes for the missing decision — never a bare retry loop, since a slow fraud-service should not stall every transfer. |
| Ledger business rejection (e.g. insufficient funds) | Yes — `FAILED` | The ledger gave a definitive, synchronous answer; no ambiguity about what happened. |
| Ledger timeout / 5xx | **No — never `FAILED`** | Money may or may not have actually moved; declaring `FAILED` here could cause a user to be told "it failed" while their balance already changed. The transfer stays `PROCESSING` until the recovery worker resolves it, using the *same* `source_id` so any retried posting call is idempotent. |

## Recovery path (not shown above)

When a ledger call times out, a background **recovery worker** (built in
Phase 3) periodically:

1. Finds transfers stuck in `PROCESSING` past a threshold.
2. Retries `POST /internal/v1/postings` with the same `source_id` — safe,
   because `ledger-service` enforces `UNIQUE (source_service, source_id,
   type)` and returns the existing posting if one already exists rather
   than creating a duplicate.
3. If a posting is found (either from the retry or from
   `GET /internal/v1/postings/{source_id}`), the transfer is moved to its
   correct terminal state based on that posting's outcome.

The same reconciliation job described in ADR-0002 independently verifies
no transfer is stuck in `PROCESSING` indefinitely, as a second safety net
on top of the recovery worker.

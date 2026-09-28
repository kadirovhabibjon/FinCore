# Payment and Refund Sagas — Sequence Diagrams

Spec Section 11, orchestrated by `payment-service` — drawn from the
implementation (`services/payment-service/app/services/payments.py`,
`refunds.py`, `expiration.py`, `recovery.py`). A payment differs from a
transfer ([transfer-saga.md](transfer-saga.md)) in that money is first
**reserved** as a hold on the payer's wallet and then **captured** into
the currency's pooled `MERCHANT_SETTLEMENT` account (ADR-0002).

## Payment: fraud check -> hold -> capture

```mermaid
sequenceDiagram
    autonumber
    actor Payer
    participant GW as Gateway
    participant PAY as payment-service
    participant FRAUD as fraud-service
    participant LEDGER as ledger-service
    participant DB as payment_db (+ outbox)

    Payer->>GW: POST /api/v1/payments (JWT, Idempotency-Key)
    GW->>PAY: forward
    PAY->>LEDGER: GET /api/v1/wallets/{source} (payer's own JWT)
    PAY->>DB: merchant exists and is ACTIVE? (404 / 409 if not)
    PAY->>DB: idempotency key, then insert Payment (CREATED)
    PAY->>FRAUD: POST /internal/v1/risk-checks

    alt BLOCK
        PAY->>DB: Payment -> FAILED + outbox payment.failed
    else REVIEW
        PAY->>DB: Payment stays CREATED (no event)
    else ALLOW
        PAY->>DB: Payment -> PROCESSING
        PAY->>LEDGER: POST /internal/v1/holds (source_id = payment.id, TTL)
        alt hold rejected (insufficient available balance, ...)
            PAY->>DB: Payment -> FAILED + outbox payment.failed
        else hold outcome unknown
            Note over PAY: stays PROCESSING, no hold_id recorded —<br/>recovery worker re-sends the same hold request
        else hold placed
            LEDGER-->>PAY: 201 hold (funds now held, not moved)
            PAY->>DB: record hold_id
            PAY->>LEDGER: POST /internal/v1/holds/{hold_id}/capture
            alt captured
                LEDGER->>LEDGER: posting: payer wallet -> MERCHANT_SETTLEMENT<br/>hold CAPTURED (partial capture releases the rest)
                PAY->>DB: Payment -> SUCCESS + outbox payment.completed
            else capture rejected (e.g. hold expired)
                PAY->>LEDGER: POST /internal/v1/holds/{hold_id}/release (best effort)
                PAY->>DB: Payment -> FAILED + outbox payment.failed
            else capture outcome unknown
                Note over PAY: stays PROCESSING with hold_id —<br/>recovery worker re-sends the capture,<br/>never a second hold
            end
        end
    end
    PAY-->>Payer: 201 + Payment
```

Every status change above is an atomic `UPDATE ... WHERE status =
:expected`, and only the caller whose update applies writes the outbox
event — so the saga's own call and the recovery worker can race on the
same payment without emitting an event twice.

## Refund: a new posting, never an edit

```mermaid
sequenceDiagram
    autonumber
    actor Owner as Merchant owner
    participant PAY as payment-service
    participant LEDGER as ledger-service
    participant DB as payment_db (+ outbox)

    Owner->>PAY: POST /api/v1/payments/{id}/refunds (JWT, Idempotency-Key)
    PAY->>DB: caller owns the payment's merchant? (404 if not)
    PAY->>DB: payment SUCCESS or PARTIALLY_REFUNDED? (409 if not)
    PAY->>DB: amount <= captured - already refunded? (422 if not)
    PAY->>DB: idempotency key, then insert Refund (PENDING)
    PAY->>LEDGER: GET /internal/v1/accounts/system?kind=MERCHANT_SETTLEMENT
    PAY->>LEDGER: POST /internal/v1/postings (source_id = refund.id)<br/>DEBIT settlement, CREDIT payer's wallet
    alt posting created
        PAY->>DB: Refund -> COMPLETED<br/>refunded_amount += amount (CHECK <= captured amount)<br/>Payment -> PARTIALLY_REFUNDED or REFUNDED<br/>+ outbox payment.refunded
    else rejected
        PAY->>DB: Refund -> FAILED
    else unknown
        Note over PAY: stays PENDING — recovery worker re-sends it
    end
    PAY-->>Owner: 201 + Refund
```

The over-refund check before the posting is only the fast path. Two
concurrent refunds that are each valid alone but together exceed the
captured amount are stopped by the database: the
`ck_payments_refunded_amount_within_bounds` CHECK constraint rejects
whichever increment loses the race.

## Background workers

| Worker | Finds | Does |
|---|---|---|
| Recovery | Payments `PROCESSING`, refunds `PENDING`, transfers `PROCESSING`, older than the stuck threshold | Re-sends exactly the step that didn't confirm (hold, capture, or refund posting) — all idempotent on `source_id` |
| Expiration | Payments still `CREATED` past `PAYMENT_REVIEW_TTL_SECONDS` (a `REVIEW` nobody resolved) | `CREATED -> EXPIRED` + `payment.failed`. No hold exists yet at `CREATED`, so there is nothing to release |
| Outbox relay | Unpublished outbox rows | Publishes them to the `payments` / `transfers` topics — see [event-flow.md](event-flow.md) |

A hold that is never captured is expired lazily on ledger-service's side
after its TTL, releasing the funds even if payment-service never comes
back to it.

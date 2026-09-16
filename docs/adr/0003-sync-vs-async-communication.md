# ADR-0003: Synchronous vs Asynchronous Communication

## Status

Accepted

## Context

FinCore is a microservices system, so every cross-service interaction must
pick one of two communication styles, and the choice has real consequences:

* **Synchronous** (internal REST) couples the caller's availability to the
  callee's availability, but lets the caller make an immediate decision
  based on the result.
* **Asynchronous** (domain event via the outbox + Kafka) decouples
  availability — the callee doesn't even need to be up when the event is
  published — but the caller can never wait for or depend on the outcome
  within its own request.

Leaving this choice implicit (as the original v1 spec did) means every new
cross-service call would be decided ad hoc, producing an inconsistent
system where some things that should be event-driven end up as blocking
calls, and vice versa. Section 3.1.4 and Section 10 of the spec already
imply a rule through the transfer saga; this ADR makes that rule explicit
and gives it a name so it is applied consistently as new services are
built.

## Decision

**Rule:** use a synchronous internal call when, and only when, the caller
cannot correctly continue its own transaction without the result. Use an
asynchronous domain event for everything else.

### Where synchronous calls are used

| Caller | Callee | Why synchronous |
|---|---|---|
| `payment-service` | `ledger-service` (`POST /internal/v1/postings`, `/holds`) | The saga's next state (`COMPLETED` vs `FAILED` vs stays `PROCESSING`) depends directly on whether the posting succeeded. There is no correct way to proceed without this answer. |
| `payment-service` | `fraud-service` (`POST /internal/v1/risk-checks`) | Whether the operation is allowed to reach the ledger at all depends on the risk decision. |

No other synchronous internal call exists in the v1 design. In particular,
`ledger-service`, `fraud-service`, `notification-service`,
`webhook-service`, and `audit-service` never make synchronous calls to
other FinCore services — this is what keeps `ledger-service` the most
stable context in the system (Section 3 of `context-map.md`).

### Where async events are used

Everything downstream of a completed state change that only needs to
*react*, not *decide*: `notification-service`, `webhook-service`,
`audit-service`, and `payment-service`'s own reconciliation/recovery path
consuming `ledger.posting.completed`. These are delivered through the
transactional outbox (formalized in ADR-0004) and never block the producer.

### Rules for every synchronous call

Every synchronous internal call must define, up front, its behavior for
each of these three failure modes (per spec Section 30, Rule 20):

1. **Timeout.** Every internal HTTP client call has an explicit timeout
   (connect + read). A timeout is never interpreted as failure of the
   underlying operation — it means the outcome is **unknown**. The caller
   must not mark its own state as `FAILED` on a timeout; it stays in a
   non-terminal state (e.g. `PROCESSING`) until the outcome is resolved by
   retry or by a recovery worker querying the callee's state.
2. **Duplicate delivery.** Any retry of a synchronous call must be safe to
   repeat. This is only possible because the callee's operation is
   idempotent by construction: `ledger-service` postings are keyed by
   `(source_service, source_id, type)`, and holds are keyed by
   `(source_service, source_id)`. `payment-service` always retries with
   the *same* `source_id` (its own operation id), never a new one.
3. **Partial failure (5xx, connection reset).** Treated the same as a
   timeout — outcome unknown, no terminal failure state, retry with the
   same idempotency key, or fall back to a reconciliation/recovery pass if
   retries are exhausted.

Concretely, for the two synchronous calls in v1:

| Call | Timeout | On timeout / 5xx | Retry policy |
|---|---|---|---|
| `payment-service → fraud-service` | Short (low hundreds of ms) | Apply the configured fail-open/fail-closed policy (Section 12 of the spec) — this is a deliberate fallback, not a bare retry, because a slow fraud-service should not stall every payment indefinitely. | No blind retry; the failure policy substitutes for the missing decision. |
| `payment-service → ledger-service` | A few seconds | Outcome is **unknown**. Transfer stays `PROCESSING`. A recovery worker retries the same posting call (idempotent) or queries `GET /internal/v1/postings/{source_id}` to learn the real outcome. | Retried by the recovery worker, not inline in the original request — the original HTTP request to the client should not hang indefinitely waiting for internal retries. |

### What synchronous calls are never used for

A synchronous call is never used purely to keep two services' data
"roughly in sync" (e.g. `ledger-service` calling back into
`payment-service` to say "by the way, here's the posting" — that is an
event, not a call) and never used where the caller could instead just wait
for an async event and poll/GET when it needs current state.

## Consequences

* `payment-service` needs an httpx client with per-call timeouts configured
  for both `ledger-service` and `fraud-service`, plus a recovery worker
  (Phase 3) that resolves `PROCESSING` transfers whose synchronous ledger
  call outcome was unknown.
* Because `ledger-service` and `fraud-service` never call out synchronously
  themselves, they can be deployed, scaled, and taken down independently
  without cascading a synchronous failure into the rest of the system.
* Every future new service must be evaluated against the same rule before
  it gets a synchronous internal client: "does the caller need this answer
  to continue its own transaction?" If no, it gets an event, not a call.

## Alternatives Considered

* **Everything synchronous** (simplest to reason about locally) — rejected:
  it would make `notification-service`/`webhook-service`/`audit-service`
  availability a hard dependency for every payment, which contradicts
  Section 3.1's design principle and turns transient notification outages
  into payment outages.
* **Everything asynchronous, including the ledger call** (fully
  decoupled) — rejected: `payment-service` genuinely cannot decide the
  transfer's terminal state without knowing whether the posting succeeded;
  making even this async would mean every transfer response to the client
  is "pending" with no way to synchronously report success, which
  contradicts the saga design in Section 10.

# FinCore — Glossary

Shared vocabulary for the whole system. Every service, ADR, and diagram uses
these terms with exactly this meaning. If a new term is needed, it is added
here before it is used in code.

---

## Money & Ledger

**Minor unit**
The smallest unit of a currency for storage purposes (e.g. tiyin for UZS,
cent for USD). All amounts are stored as integers in minor units
(`amount_minor`, `BIGINT`), never as `float` or `Decimal` in the database.
See [ADR-0001](adr/0001-money-representation.md).

**Ledger**
The append-only, double-entry record of every money movement in FinCore. It
is the single source of truth for money; wallet balances are a projection
of it. Owned by `ledger-service`.

**Ledger account**
Any account that can be debited or credited in the ledger. Two categories:
- **User wallet** — a customer-facing ledger account (`USER_WALLET`).
- **System account** — an internal counterpart account not owned by a user
  (`EXTERNAL_FUNDING`, `EXTERNAL_PAYOUT`, `MERCHANT_SETTLEMENT`, `FEES`,
  `SUSPENSE`).

**Wallet**
A `USER_WALLET`-kind ledger account owned by a single user for a single
currency. One wallet per `(owner_user_id, currency)`.

**Posting**
A balanced, atomic accounting fact: a set of ledger entries where
`sum(DEBIT) == sum(CREDIT)` for a single currency. A posting is immutable
once written. Identified by `(source_service, source_id, type)` for
idempotency.

**Ledger entry**
One line of a posting: a single `(account_id, direction, amount_minor)`
tuple. Entries are append-only and always belong to exactly one posting.

**Direction**
`DEBIT` or `CREDIT`. What a debit or credit *means* (increase or decrease)
depends on the account's **normal balance side** — see
[ADR-0002](adr/0002-ledger-model.md).

**Normal balance side**
The direction (DEBIT or CREDIT) on which a given account kind's balance
*increases*. Defined per account kind in ADR-0002.

**Account balance**
The current projected balance of a ledger account (`balance_minor`), derived
from the sum of its entries. Cached/materialized for read performance but
always reconstructable from the entry log.

**Hold**
A temporary reservation of funds on a wallet (`held_minor`) that reduces
*available* balance without moving money. Used for two-step payment flows
(reserve → capture / release). A hold does **not** produce a posting; only
its capture does.

**Available balance**
`balance_minor - held_minor`. The amount a wallet owner can actually spend.
Must never go negative — enforced by a CHECK constraint.

**Reversal**
A new posting that undoes the effect of a previous posting by swapping its
debits and credits. Used to correct mistakes; the original posting is never
edited or deleted.

**Reconciliation**
A periodic job that verifies ledger invariants hold: every posting is
balanced, every account balance equals the sum of its entries, and no
business operation is stuck in `PROCESSING` past a threshold.

---

## Business Operations (payment-service)

**Business operation**
A user-facing intention to move money: `TRANSFER`, `PAYMENT`, `DEPOSIT`,
`WITHDRAWAL`, `REFUND`. Owned by `payment-service`. Distinct from a
*posting*, which is the accounting fact it produces. See Section 7 of the
spec.

**Transfer**
A business operation moving money between two wallets inside FinCore.

**Payment**
A business operation moving money from a user wallet to a merchant, using a
hold → capture flow.

**Saga**
A sequence of local transactions across services, coordinated by
`payment-service`, where each step has a defined compensating or recovery
action if a later step fails. FinCore uses an **orchestrated** saga (no
distributed transaction / 2PC).

**State machine**
The explicit set of allowed status transitions for a business operation
(e.g. `PENDING → PROCESSING → COMPLETED`). Invalid transitions are rejected
in code and guarded at the DB level with `WHERE status = :expected`.

---

## Idempotency

**Idempotency key**
A client-supplied key (`Idempotency-Key` header) scoped per user that lets
`payment-service` detect and safely respond to a retried request without
repeating its side effects.

**Request fingerprint**
A hash of method + path + canonical request body, stored alongside an
idempotency key. Used to detect a key being reused with a *different*
request body (rejected with `422`).

**Internal idempotency**
Idempotency enforced between services via database uniqueness, e.g. a
posting's `UNIQUE (source_service, source_id, type)` constraint, or a
consumer's `processed_events (event_id PRIMARY KEY)` table.

---

## Async / Events

**Outbox event**
A row written in the *same local transaction* as a business change,
guaranteeing an event is never lost or emitted for a rolled-back operation.
Relayed to Kafka by a separate worker. See
[ADR-0004](adr/0004-broker-choice.md) and Section 14.1 of the spec.

**Outbox relay**
The worker process that reads unpublished `outbox_events` rows, publishes
them to Kafka, and marks them published. Delivery is at-least-once.

**Event envelope**
The standard wrapper around every event's payload:
`event_id, event_type, event_version, occurred_at, producer, correlation_id, data`.

**Consumer group**
A named group of Kafka consumers that share the work of reading a topic's
partitions. Each downstream service (`notification`, `webhook`, `audit`,
and `payment-service` when reacting to ledger events) runs its own
consumer group so each gets every event independently.

**Dead-letter topic (DLT)**
Where an event lands after exhausting its retry budget. Requires manual
inspection/replay; triggers an alert.

**Processed events table**
A per-consumer table (`processed_events(event_id PRIMARY KEY)`) written in
the same transaction as the event's side effect, making consumption
idempotent under at-least-once delivery.

---

## Identity & Security

**JWT (JSON Web Token)**
A short-lived, asymmetrically signed (RS256/EdDSA) access token issued by
`identity-service`. Other services verify it locally using the public key
from JWKS — no network call to `identity-service` per request.

**JWKS (JSON Web Key Set)**
The public-key endpoint published by `identity-service` so other services
can verify JWTs without sharing a secret.

**Refresh token**
An opaque, long-lived token used to obtain a new access token. Stored in
the database only as a hash, never in plaintext.

**Refresh token rotation**
Every use of a refresh token issues a new one and invalidates the old one.

**Reuse detection**
If an already-rotated (invalidated) refresh token is presented again, the
entire session family is revoked — this indicates the token was stolen.

**RBAC (role-based access control)**
Authorization based on roles (`USER`, `SUPPORT`, `ADMIN`) *combined with*
resource-ownership checks — a role alone never grants access to another
user's resource.

**Service-to-service authentication**
The mechanism by which internal (`/internal/*`) endpoints authenticate
calling services rather than end users. Internal endpoints are never routed
through the gateway.

**Correlation ID**
An identifier generated at the gateway and propagated through every HTTP
call and event this request causes, enabling a single request to be traced
across all services.

---

## Fraud / Risk

**Fraud check**
A synchronous risk evaluation performed by `fraud-service` for a business
operation, producing a decision (`ALLOW`, `REVIEW`, `BLOCK`) and a score.
Always persisted, even on `ALLOW`.

**Fail-open / fail-closed**
The policy applied when `fraud-service` is unavailable or times out:
fail-open allows low-risk amounts through (flagged), fail-closed forces
higher-risk amounts into `REVIEW`. Configurable, documented in an ADR.

---

## Concurrency

**Row lock (`SELECT ... FOR UPDATE`)**
A pessimistic lock taken on ledger account rows before checking balance and
writing entries, preventing two concurrent postings from double-spending
the same balance.

**Lock ordering**
Always locking accounts involved in a posting in ascending `account_id`
order, so two transfers in opposite directions cannot deadlock each other.

**TOCTOU (time-of-check-to-time-of-use)**
The race condition where a balance is checked, then used, with no lock in
between — two concurrent requests can both pass the check. FinCore avoids
this by checking balance *after* the row lock, inside the same transaction.

**Optimistic locking**
Using a `version` column to detect concurrent modification instead of
holding a row lock. Not used for balance updates in FinCore (pessimistic
locking is used there); may be used elsewhere.

---

## Services & Boundaries

**Business capability**
A cohesive unit of what the system does for the business (e.g. "move money
between wallets"). FinCore's service boundaries are drawn around business
capabilities plus their consistency requirements — never one service per
table. See Section 3 of the spec.

**Database-per-service**
Each service owns its own database; no service reads or writes another
service's tables directly. Cross-service data needs are served by API calls
or events.

**Internal endpoint**
An API endpoint under `/internal/v1/*`, authenticated service-to-service,
never exposed through the gateway.

**Gateway**
The single entry point (Nginx) for all public traffic: routing, TLS
termination, rate limiting, request size limits, correlation ID injection.

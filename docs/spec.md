# FinCore — Digital Wallet & Payment Platform (Spec v2)

You are helping me build a serious backend portfolio project called **FinCore**.

This is not a tutorial, toy CRUD app, or a set of unrelated services. FinCore must be treated as **one complete financial backend product** built with a **microservices architecture**, which I will develop over approximately **16 weeks** to improve my backend engineering skills and use as a flagship GitHub project.

I am a Python Backend Developer. My main goal with this project is to grow from Junior toward Middle / Middle+ Backend level by learning production-oriented backend and distributed-systems engineering, in a way that resembles how real banking systems are built.

---

# 1. Project Goal

FinCore is a simplified digital wallet and payment processing platform inspired conceptually by digital wallets, payment applications, and core banking systems.

Users should eventually be able to:

* Register and authenticate
* Create and manage wallets
* Check balances
* Transfer money between users
* Make payments
* View transaction history
* Receive transaction notifications
* Have payments checked by fraud/risk rules
* Receive webhook updates
* Safely retry failed asynchronous operations
* Have every important action recorded in an audit log

The project should demonstrate real backend engineering concepts such as:

* API design
* service boundaries
* database architecture (database-per-service)
* transactions
* concurrency
* financial consistency
* double-entry bookkeeping
* idempotency
* sagas and distributed consistency
* transactional outbox
* asynchronous processing
* caching
* message brokers
* retries
* reconciliation
* security (user and service-to-service)
* testing (including contract and concurrency tests)
* monitoring and distributed tracing
* CI/CD
* Docker
* production-oriented architecture

---

# 2. Important Development Principle

Do NOT treat FinCore as multiple unrelated portfolio projects.

Everything belongs to one system. The functional domains are:

```text
FinCore
│
├── Authentication
├── Users
├── Wallets
├── Ledger
├── Transfers
├── Payments
├── Fraud Detection
├── Notifications
├── Webhooks
├── Audit Logs
└── Admin
```

Domains are grouped into services by **business capability and consistency requirements**, not one service per domain and never one service per table (see Section 3).

---

# 3. Architecture Strategy

FinCore uses a **microservices architecture**.

## 3.1 Service boundary rules

1. A service owns a business capability end to end: its API, its logic, and its data.
2. **Database-per-service.** A service never reads or writes another service's tables. No cross-service joins. Data from other services is obtained via API calls or events.
3. **Data that must change atomically stays in one service.** Wallet balances and ledger entries must always be consistent, so they live in the same service and the same database. Splitting them would require a distributed transaction for every money movement, which real banks avoid.
4. Services communicate:
   * **synchronously** (internal REST over HTTP, possibly gRPC later) when the caller needs an answer to continue;
   * **asynchronously** (domain events via a message broker) when other services only need to react.
5. Every cross-service operation must be designed for partial failure: timeouts, retries, duplicates, and unknown outcomes.
6. Shared code is limited to technical libraries (logging, config helpers, event envelope schemas). **No shared domain models and no shared database.**

## 3.2 Services

| Service | Domains | Owns data | Role |
|---|---|---|---|
| `gateway` | — | none | Nginx: routing, TLS termination, rate limiting, request size limits, correlation ID |
| `identity-service` | Authentication, Users, RBAC | users, roles, sessions, refresh tokens | Issues JWTs, publishes public keys (JWKS) |
| `ledger-service` | Wallets, Ledger, Balances | ledger accounts (wallets + system accounts), postings, entries, balances, holds | **Core banking. Source of truth for money.** |
| `payment-service` | Transfers, Payments, Refunds, Merchants | transfers, payments, refunds, merchants, idempotency keys | Orchestrates money flows (sagas) |
| `fraud-service` | Fraud / Risk | fraud checks, rule configs, counters | Synchronous risk decisions |
| `notification-service` | Notifications | notifications, delivery attempts | Event consumer |
| `webhook-service` | Webhooks | endpoints, deliveries, attempts | Event consumer, signed delivery |
| `audit-service` | Audit Logs | append-only audit records | Event consumer |

Admin is not a separate service. Admin/support endpoints live inside the owning service and are protected by RBAC.

## 3.3 Architecture diagram

```text
                          Client
                            │
                            ▼
                ┌───────────────────────┐
                │   Gateway (Nginx)     │
                └───────────┬───────────┘
                            │ HTTP (JWT)
      ┌───────────┬─────────┼──────────────┬──────────────┐
      ▼           ▼         ▼              ▼              ▼
 identity-    payment-   ledger-        webhook-      notification-
 service      service    service        service       service (read API)
    │          │  │  │      │
    │          │  │  └──────┘  internal sync call: postings / holds
    │          │  │
    │          │  └──► fraud-service   (internal sync call, timeout)
    │          │
    ▼          ▼          ▼             ▼
 [identity_db][payment_db][ledger_db] [fraud_db]   ... one DB per service
    │          │          │             │
    └──────────┴── outbox ┴─────────────┘
                    │ (relay)
                    ▼
               ┌─────────┐
               │  Kafka  │
               └────┬────┘
      ┌─────────────┼──────────────┬──────────────┐
      ▼             ▼              ▼              ▼
 notification-   webhook-       audit-        payment-service
 service         service        service       (reacts to ledger events)

 Redis: rate limits, OTP, token denylist, fraud counters (never money)
```

## 3.4 Why services are split this way

* **identity-service** is separate because authentication has different security, scaling and change patterns from money movement.
* **ledger-service** is the most protected service. It knows nothing about users' intentions (transfer vs payment); it only accepts balanced postings and holds. This mirrors a core banking ledger.
* **payment-service** contains transfers, payments and refunds together because they share the same orchestration machinery (idempotency, state machines, sagas, fraud calls). Splitting them would duplicate that machinery.
* **fraud-service** is separate so the rule engine can later be replaced by an ML model without touching payment logic.
* **notification / webhook / audit** are pure event consumers: they are the natural asynchronous boundaries.

---

# 4. Core Technology Stack

Per service:

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2.x (async)
Alembic (migrations per service)
PostgreSQL (one database per service)
httpx (internal HTTP clients with timeouts)
```

Infrastructure:

```text
Nginx (gateway)
Redis
Kafka (see ADR; chosen for durable event log, multiple consumer groups, replay for audit)
Docker
Docker Compose
```

Testing:

```text
pytest
pytest-asyncio
httpx
testcontainers (real PostgreSQL / Kafka in tests)
```

Production/dev tooling:

```text
Git
GitHub
GitHub Actions
Prometheus
Grafana
OpenTelemetry + Jaeger/Tempo (distributed tracing is required in microservices)
```

Possible later additions:

```text
gRPC for internal calls
MinIO / S3
HashiCorp Vault
Kubernetes
```

Do not introduce technology unless there is a real reason for using it.

---

# 5. Main Domains

## Authentication (identity-service)

Responsibilities:

* registration
* login
* logout
* password hashing (Argon2id or bcrypt)
* JWT access tokens (short-lived, signed with RS256/EdDSA so other services can verify with the public key via JWKS)
* refresh tokens (opaque, stored **only as a hash** in the database)
* refresh token rotation with **reuse detection** (reusing an old refresh token revokes the whole session family)
* session management
* role-based access control
* optional 2FA later

Possible roles:

```text
USER
SUPPORT
ADMIN
```

---

## Users (identity-service)

Contains user profile and account information.

Example:

```text
User
- id (UUID)
- email (unique, normalized)
- phone (unique)
- password_hash
- first_name
- last_name
- status
- created_at
- updated_at
```

Possible statuses:

```text
ACTIVE
BLOCKED
SUSPENDED
```

Other services do not store copies of user profiles. When they need user status, they rely on JWT claims or an internal identity API; user status changes are also published as events (`user.blocked`, etc.).

---

# 6. Wallet System (ledger-service)

A user can have wallets. A wallet is a customer-facing **ledger account**.

Example:

```text
Wallet (ledger account of kind USER_WALLET)
- id (UUID)
- owner_user_id
- currency
- status
- created_at
```

Constraint: one wallet per `(owner_user_id, currency)` in v1.

Initially support:

```text
UZS
USD
```

Wallet statuses:

```text
ACTIVE
FROZEN
CLOSED
```

Balance must NOT be implemented carelessly as:

```python
wallet.balance -= amount
```

## 6.1 Money representation

* Money is stored as **integer minor units** in `BIGINT` columns (e.g., `amount_minor`), together with a currency code (ISO 4217). Minor unit exponent is defined per currency in configuration.
* `float` is never used for money anywhere: not in the DB, not in Python, not in JSON.
* In the public API, amounts are sent as **decimal strings** (e.g., `"100000.00"`) and converted with `Decimal` at the boundary; invalid precision is rejected.
* This decision is documented in an ADR.

## 6.2 Currency rule for v1

* v1 supports **same-currency operations only**. A UZS wallet can only send to a UZS wallet.
* Currency exchange (FX rates, rate source, spread, FX ledger accounts) is explicitly out of scope for v1 and may be a later phase.

Financial consistency must be one of the core learning areas of this project.

---

# 7. Transaction Engine

"Transaction" is an overloaded word. FinCore separates two concepts:

| Concept | Service | Meaning |
|---|---|---|
| **Business operation** (Transfer, Payment, Refund, Deposit, Withdrawal) | payment-service | The user's intention, its lifecycle, idempotency, fraud decision |
| **Posting** (ledger transaction) | ledger-service | The accounting fact: a balanced set of ledger entries |

One business operation produces one or more postings (e.g., a payment may produce a hold, then a capture posting, later a refund posting).

## 7.1 Business operation types

```text
TRANSFER
PAYMENT
DEPOSIT
WITHDRAWAL
REFUND
```

## 7.2 Transfer example (payment-service)

```text
Transfer
- id (UUID)
- reference (human-readable, unique)
- initiator_user_id
- source_wallet_id
- destination_wallet_id
- amount_minor
- currency
- status
- failure_reason
- fraud_decision
- description
- idempotency_key_id
- created_at
- updated_at
- completed_at
```

Deposits have no source wallet and payments have a merchant destination, so each operation type has its own table/model instead of forcing everything into one table with nullable columns.

## 7.3 Status state machine

Transfer statuses:

```text
PENDING
PROCESSING
COMPLETED
FAILED
CANCELLED
```

Allowed transitions (anything else is rejected in code and guarded in the DB update with `WHERE status = :expected`):

```text
PENDING     → PROCESSING | CANCELLED | FAILED
PROCESSING  → COMPLETED  | FAILED
COMPLETED   → (terminal)
FAILED      → (terminal)
CANCELLED   → (terminal)
```

A REVIEW decision from fraud keeps the transfer in `PENDING` until a SUPPORT/ADMIN approves or rejects it.

Operations must be processed safely.

Topics we must learn and implement:

* ACID transactions
* isolation levels (READ COMMITTED vs REPEATABLE READ vs SERIALIZABLE)
* row locking (`SELECT ... FOR UPDATE`)
* deadlocks and lock ordering
* optimistic locking (version columns) vs pessimistic locking
* rollback
* duplicate requests
* retries
* race conditions
* unknown outcomes after network timeouts

---

# 8. Double-Entry Ledger (ledger-service)

The ledger is the **source of truth for money**. Wallet balances are a projection of the ledger.

Basic principle:

```text
For every posting: sum(DEBIT) == sum(CREDIT), per currency
```

## 8.1 Account kinds

Every movement needs two sides, so the ledger has system accounts in addition to user wallets:

```text
USER_WALLET           customer money held by FinCore (liability)
EXTERNAL_FUNDING      counterpart for deposits from outside
EXTERNAL_PAYOUT       counterpart for withdrawals to outside
MERCHANT_SETTLEMENT   money owed to merchants
FEES                  fee revenue
SUSPENSE              temporary holding for unresolved items
```

System accounts exist per currency.

## 8.2 Example

User A transfers 100,000 UZS to User B:

```text
Posting P1 (TRANSFER, source_id = transfer.id)
  DEBIT   A wallet (UZS)   100,000.00
  CREDIT  B wallet (UZS)   100,000.00
```

User deposits 50,000 UZS:

```text
Posting P2 (DEPOSIT)
  DEBIT   EXTERNAL_FUNDING (UZS)  50,000.00
  CREDIT  User wallet (UZS)       50,000.00
```

(Debit/credit sign convention per account kind is defined in an ADR.)

## 8.3 Structure

```text
LedgerAccount
- id
- kind
- owner_user_id (nullable for system accounts)
- currency
- status
- created_at

Posting
- id
- source_service
- source_id              (e.g., transfer id)
- type
- currency
- created_at
- UNIQUE (source_service, source_id, type)   ← posting idempotency

LedgerEntry
- id
- posting_id
- account_id
- direction (DEBIT | CREDIT)
- amount_minor (> 0)
- currency
- created_at

AccountBalance
- account_id (PK)
- balance_minor
- held_minor
- version
- updated_at
- CHECK (balance_minor - held_minor >= 0) for USER_WALLET accounts
```

## 8.4 Ledger rules

* Ledger entries and postings are **append-only**. They are never UPDATEd or DELETEd. Mistakes are corrected by a **reversal posting**.
* A posting, its entries, balance updates and its outbox event are written in **one local database transaction**.
* A posting is rejected unless debits equal credits and all accounts share its currency.
* Accounts involved in a posting are locked with `SELECT ... FOR UPDATE` **in a deterministic order (ascending account id)** to prevent deadlocks.
* The balance check happens **after** the lock is acquired, inside the transaction.
* Database constraints (CHECK, FK, UNIQUE, NOT NULL) are the last line of defense against code bugs.
* **Holds** (reserve → capture / release) support merchant payments and two-step flows.
* A **reconciliation job** periodically verifies: every posting is balanced, `AccountBalance` equals the sum of entries, and no business operation is stuck in `PROCESSING` longer than a threshold.

Ledger implementation must be designed carefully before coding.

---

# 9. Idempotency

## 9.1 Public API idempotency (payment-service)

Payment APIs must support idempotency.

Example request:

```http
POST /api/v1/transfers
Idempotency-Key: f712ab...
```

If the same request accidentally arrives twice, money must NOT be transferred twice.

Design:

```text
IdempotencyKey
- id
- user_id
- key
- request_fingerprint   (hash of method + path + canonical body)
- status                (IN_PROGRESS | COMPLETED)
- response_status_code
- response_body
- resource_id
- created_at
- expires_at
- UNIQUE (user_id, key)
```

Behavior:

* Key is scoped **per user**.
* First request inserts `IN_PROGRESS` (the UNIQUE constraint wins races between concurrent duplicates).
* Same key + same fingerprint + `COMPLETED` → return the stored response.
* Same key + same fingerprint + `IN_PROGRESS` → return `409 Conflict` (request still processing).
* Same key + different fingerprint → return `422 Unprocessable Entity`.
* Keys expire after a TTL (e.g., 24h).
* Redis may be used as an optimization, but the PostgreSQL constraint is authoritative.

## 9.2 Internal idempotency

* Ledger postings are idempotent via `UNIQUE (source_service, source_id, type)`. Retrying a posting call returns the existing posting instead of creating a new one.
* Event consumers are idempotent via a `processed_events (event_id PRIMARY KEY)` table written in the same transaction as their side effect.

We must understand:

* idempotency keys
* request fingerprints
* duplicate request detection
* stored responses
* database uniqueness constraints
* idempotency across service boundaries

---

# 10. Transfers

Main use case:

```text
User A
   │
   │ 100,000 UZS
   ▼
User B
```

## 10.1 Corrected flow (saga orchestrated by payment-service)

```text
Request → Gateway
   ↓
payment-service: verify JWT (public key), authorize (user owns source wallet)
   ↓
Validate request (amount > 0, precision, same currency, source ≠ destination)
   ↓
Idempotency check (Section 9) → insert IN_PROGRESS
   ↓
Create Transfer (PENDING)                     [local tx, payment_db]
   ↓
Call fraud-service (timeout, see Section 12)
   ├── BLOCK  → Transfer FAILED  + outbox transfer.failed
   ├── REVIEW → stays PENDING    + outbox fraud.review_required
   └── ALLOW  ↓
Transfer PENDING → PROCESSING                  [local tx]
   ↓
Call ledger-service POST /internal/postings
  (idempotent by source_id = transfer.id)
        ledger-service, ONE local transaction:
          lock both accounts in ascending id order (FOR UPDATE)
          check wallet status and available balance (after lock)
          insert posting + entries
          update balances
          insert outbox event ledger.posting.completed
          commit
   ↓
Result:
   ├── success            → Transfer COMPLETED + outbox transfer.completed   [local tx]
   ├── business rejection → Transfer FAILED    + outbox transfer.failed      (e.g. insufficient funds)
   └── timeout / 5xx      → outcome UNKNOWN: do NOT mark FAILED.
                            Retry with the same source_id, or query posting status.
                            Recovery worker + reconciliation resolve stuck PROCESSING.
   ↓
Store idempotent response (COMPLETED)
   ↓
Outbox relay publishes events to Kafka
   ↓
notification-service / webhook-service / audit-service react
```

Key rules:

* Balance is never checked outside the ledger lock.
* Domain events are never published directly after commit; they are written to the **transactional outbox** in the same local transaction.
* A network timeout is never treated as a failure of money movement.

---

# 11. Payments (payment-service)

The platform supports a simplified merchant/payment flow.

```text
User
  ↓
Payment API (payment-service)
  ↓
Ledger hold → capture
  ↓
Merchant settlement account
```

Payment statuses and transitions:

```text
CREATED     → PROCESSING | FAILED | EXPIRED
PROCESSING  → SUCCESS | FAILED
SUCCESS     → REFUNDED (full) | PARTIALLY_REFUNDED
PARTIALLY_REFUNDED → REFUNDED
FAILED, EXPIRED, REFUNDED → terminal
```

Later support:

* refunds (as new postings, never by editing old ones; total refunds ≤ captured amount)
* payment expiration (holds released automatically)
* merchant callbacks
* webhook delivery

---

# 12. Fraud / Risk Engine (fraud-service)

Do not start with Machine Learning.

Start with a rule-based fraud detection engine.

Possible rules:

```text
Very large payment
Too many payments in a short period
New device
Suspicious IP
Unusual transaction frequency
Repeated failed payments
```

Example scoring:

```text
amount > threshold        +30
new_device                +20
high_frequency            +25
suspicious_ip             +40
```

Risk result:

```text
0–39   → ALLOW
40–69  → REVIEW
70+    → BLOCK
```

Every check is stored (`fraud_checks`) with the rules triggered and the score, for audit and tuning.

Failure policy (fraud-service unavailable or timeout):

```text
amount ≤ low-risk limit  → ALLOW with flag "fraud_unavailable" (fail-open, logged + alerted)
amount > low-risk limit  → REVIEW (fail-closed)
```

The policy is configurable and documented in an ADR.

The rule engine is implemented behind a stable interface (Strategy pattern), so it can later be replaced or supplemented by an ML model without rewriting the payment system.

---

# 13. Redis

Redis should be used where justified.

Possible uses:

```text
rate limiting
temporary OTP data
token/session denylist
cached user data
fraud counters (sliding windows)
idempotency optimization (cache in front of the DB record)
```

Each service uses its own key prefix (or its own logical DB); services do not read each other's Redis data.

PostgreSQL remains the source of truth for financial information.

Never use Redis as the authoritative financial database, and never use Redis distributed locks to protect balances — balances are protected by PostgreSQL row locks in ledger-service.

---

# 14. Message Broker

FinCore uses **Kafka** (decision recorded in an ADR; RabbitMQ trade-offs are documented there).

## 14.1 Transactional Outbox

Every service that publishes events:

1. Writes business changes **and** an `outbox_events` row in the same local DB transaction.
2. An outbox relay (worker) reads unpublished rows and publishes them to Kafka, then marks them published.
3. Delivery is therefore **at-least-once**, so all consumers must be idempotent.

```text
OutboxEvent
- id (event_id, UUID)
- aggregate_type
- aggregate_id        (used as Kafka partition key → per-aggregate ordering)
- event_type
- payload (JSONB)
- created_at
- published_at (nullable)
```

## 14.2 Event envelope

```json
{
  "event_id": "uuid",
  "event_type": "transfer.completed",
  "event_version": 1,
  "occurred_at": "2026-01-01T12:00:00Z",
  "producer": "payment-service",
  "correlation_id": "uuid",
  "data": { }
}
```

Events carry IDs and necessary facts, never secrets or full sensitive profiles.

## 14.3 Domain events

```text
user.registered
user.blocked

wallet.created

ledger.posting.completed

transfer.completed
transfer.failed

payment.completed
payment.failed
payment.refunded

fraud.detected
fraud.review_required
```

Example:

```text
Payment
   ↓
payment.completed (outbox → Kafka)
   ├── Notification consumer
   ├── Webhook consumer
   ├── Audit consumer
   └── Analytics consumer (later)
```

We need to learn:

* producers
* consumers and consumer groups
* partitions and ordering keys
* acknowledgements / offset commits
* retries
* dead-letter topics
* duplicate events
* consumer idempotency
* delivery guarantees (at-most-once, at-least-once, "exactly-once" and its limits)
* event schema versioning

---

# 15. Notification System (notification-service)

Support events such as:

```text
Transfer completed
Payment successful
Payment failed
Security warning
Login from a new device
```

Channels can initially be mocked:

```text
Email
SMS
Push
```

No paid external provider is required.

For development, logging or local mock providers are acceptable. Providers are implemented behind an interface so real ones can be added later.

---

# 16. Retry and Dead Letter Queue

Asynchronous operations can fail.

Example:

```text
payment.completed
      ↓
Notification consumer
      ↓
SMS provider unavailable
      ↓
Retry topic (delay 1)
      ↓
Retry topic (delay 2)
      ↓
Retry topic (delay 3)
      ↓
Dead-letter topic (DLT) + alert
```

We must implement and understand:

* retry policy
* exponential backoff with jitter
* maximum retries
* retry topics vs blocking retries (why blocking a partition is dangerous)
* dead-letter topics and manual replay
* permanent vs temporary failures (validation error → DLT immediately; timeout → retry)

The same principles apply to synchronous internal calls: timeouts on every call, limited retries only for idempotent operations, and circuit breaking later if justified.

---

# 17. Webhooks (webhook-service)

Merchants or external systems may register webhook endpoints.

Example event:

```json
{
  "event_id": "uuid",
  "event": "payment.completed",
  "payment_id": "...",
  "status": "SUCCESS",
  "occurred_at": "..."
}
```

Webhook system should eventually support:

* signed requests (HMAC-SHA256 over timestamp + body, header with timestamp to prevent replay)
* per-endpoint secrets (stored securely, rotatable)
* retry with backoff
* delivery history (every attempt with status code and latency)
* timeout
* failure handling (endpoint auto-disabled after repeated failures)
* idempotency (receivers deduplicate by `event_id`)
* SSRF protection (reject private/internal target addresses)

---

# 18. Audit Logging (audit-service)

Important actions must be auditable.

Examples:

```text
USER_LOGIN
USER_BLOCKED
PAYMENT_CREATED
TRANSFER_COMPLETED
TRANSFER_FAILED
ADMIN_ACTION
PASSWORD_CHANGED
```

Audit records contain: who (actor id, role), what (action), which resource, when, from where (IP, user agent), result, correlation id.

Rules:

* Audit storage is **append-only** (no UPDATE/DELETE permissions for the service's DB user).
* Audit events are delivered through the outbox, so an action that committed cannot silently lose its audit record.
* Optional later: hash chaining of records for tamper evidence.

Audit logs should contain enough information for investigation without storing sensitive secrets (no passwords, tokens, full card data, or secret keys).

---

# 19. Security

Important areas:

```text
password hashing (Argon2id / bcrypt)
JWT security (asymmetric signing, short expiry, key rotation via JWKS)
refresh token rotation with reuse detection
refresh tokens stored only as hashes
authorization (resource ownership checks, not only roles)
RBAC
service-to-service authentication (internal service tokens; mTLS later)
internal endpoints (/internal/*) not exposed through the gateway
input validation
rate limiting
secrets management
SQL injection protection
API abuse protection
secure headers
audit logging
least-privilege DB users per service
```

Never put real secrets into GitHub.

Use:

```text
.env (per service, git-ignored) + .env.example
```

for local development initially.

Later study:

```text
HashiCorp Vault
```

---

# 20. API Versioning

Use:

```text
/api/v1/
```

Public endpoints (routed by the gateway to the owning service):

```text
POST   /api/v1/auth/register            → identity-service
POST   /api/v1/auth/login               → identity-service
POST   /api/v1/auth/refresh             → identity-service
POST   /api/v1/auth/logout              → identity-service

GET    /api/v1/users/me                 → identity-service

POST   /api/v1/wallets                  → ledger-service
GET    /api/v1/wallets                  → ledger-service
GET    /api/v1/wallets/{id}             → ledger-service
GET    /api/v1/wallets/{id}/entries     → ledger-service

POST   /api/v1/transfers                → payment-service
GET    /api/v1/transfers/{id}           → payment-service

POST   /api/v1/payments                 → payment-service
GET    /api/v1/payments/{id}            → payment-service

GET    /api/v1/transactions             → payment-service (user-facing history of business operations)
GET    /api/v1/transactions/{id}        → payment-service
```

Internal endpoints (not exposed through the gateway, service-authenticated):

```text
POST   /internal/v1/postings            → ledger-service
GET    /internal/v1/postings/{source_id}
POST   /internal/v1/holds               → ledger-service
POST   /internal/v1/holds/{id}/capture
POST   /internal/v1/holds/{id}/release
POST   /internal/v1/risk-checks         → fraud-service
```

Errors use a consistent format (RFC 7807 Problem Details) across all services.

Exact endpoints can evolve as the architecture becomes clearer.

---

# 21. Database

Main database:

```text
PostgreSQL — one logical database (and one DB user) per service
```

Locally a single PostgreSQL container may host several databases, but services still cannot access each other's databases.

Initial ownership:

```text
identity_db:     users, roles, user_roles, sessions, refresh_tokens, outbox_events

ledger_db:       ledger_accounts, postings, ledger_entries, account_balances,
                 holds, outbox_events

payment_db:      transfers, payments, refunds, merchants, idempotency_keys,
                 outbox_events, processed_events

fraud_db:        fraud_checks, fraud_rules

notification_db: notifications, notification_attempts, processed_events

webhook_db:      webhook_endpoints, webhook_deliveries, webhook_attempts,
                 processed_events

audit_db:        audit_logs, processed_events
```

Every schema decision should be explained before implementation, including relationships, constraints and indexes.

Use Alembic for migrations (separate migration history per service).

Never manually modify production-style database schemas.

---

# 22. Project Structure

Monorepo with independent services:

```text
fincore/
│
├── services/
│   ├── identity-service/
│   │   ├── app/
│   │   │   ├── api/v1/
│   │   │   ├── core/          (config, security, logging, exceptions)
│   │   │   ├── db/            (base, session)
│   │   │   ├── domain/        (models, business rules)
│   │   │   ├── repositories/
│   │   │   ├── services/      (use cases)
│   │   │   ├── events/        (outbox)
│   │   │   └── main.py
│   │   ├── migrations/
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   └── integration/
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── pyproject.toml
│   │   └── .env.example
│   │
│   ├── ledger-service/
│   ├── payment-service/
│   ├── fraud-service/
│   ├── notification-service/
│   ├── webhook-service/
│   └── audit-service/
│
├── libs/
│   └── fincore-common/        (logging, config helpers, event envelope, tracing;
│                               NO domain models)
│
├── contracts/
│   ├── openapi/               (public + internal API specs)
│   └── events/                (event schemas, versioned)
│
├── gateway/
│   └── nginx/
│
├── tests/
│   └── e2e/                   (cross-service scenarios)
│
├── infra/
│   ├── prometheus/
│   └── grafana/
│
├── docs/
│   ├── adr/
│   ├── diagrams/
│   └── glossary.md
│
├── docker-compose.yml
├── Makefile
└── README.md
```

Do not blindly create all services and directories on day one.

Create services and components when the roadmap reaches them.

---

# 23. Testing Strategy

Testing is mandatory.

We should eventually have:

```text
Unit tests                (domain rules, state machines, fraud rules)
Integration tests         (service + real PostgreSQL via testcontainers)
API tests
Database transaction tests
Concurrency tests         (parallel transfers from one wallet; opposite-direction transfers for deadlocks)
Idempotency tests         (sequential and concurrent duplicates)
Authentication tests
Payment tests
Ledger consistency tests
Contract tests            (API and event schemas between services)
Saga failure tests        (ledger timeout, fraud unavailable, duplicate events)
End-to-end tests          (docker compose, full flows through the gateway)
```

Concurrency and locking tests must run against **real PostgreSQL**, never SQLite.

Critical financial logic should have strong test coverage.

Invariants that must always remain true:

```text
per posting:  sum(debits) == sum(credits)
per account:  account_balances.balance_minor == sum of its entries (signed)
per wallet:   available balance never below zero
per transfer: at most one posting for its source_id
```

---

# 24. Observability

Required from the start of multi-service work:

```text
structured JSON logging
correlation ID propagated through gateway, HTTP calls and Kafka events
distributed tracing (OpenTelemetry)
health checks (liveness)
readiness checks (DB, Kafka connectivity)
```

Later add:

```text
Prometheus metrics
Grafana dashboards
alerts
```

Useful metrics:

```text
HTTP request count (per service)
HTTP latency
internal call latency and error rate
payment count
failed payment count
transfer count
transfers stuck in PROCESSING
fraud blocks
outbox backlog (unpublished events)
Kafka consumer lag
DLT message count
reconciliation mismatches
DB connection usage
```

---

# 25. Docker

The entire development environment should eventually start with something similar to:

```bash
docker compose up -d
```

Possible containers:

```text
gateway (nginx)
identity-service
ledger-service
payment-service
fraud-service
notification-service
webhook-service
audit-service
outbox relays / workers
postgres
redis
kafka
kafka-ui
jaeger
prometheus
grafana
```

Add infrastructure gradually.

Do not create unnecessary infrastructure before the application needs it.

---

# 26. CI/CD

GitHub Actions should eventually run, **per changed service**:

```text
lint (ruff) + type check (mypy)
unit tests
integration tests (testcontainers)
migration checks (upgrade from empty DB + downgrade sanity)
contract checks
Docker image build
```

Plus e2e tests on the main branch.

Pull requests should not pass if critical tests fail.

---

# 27. Development Roadmap (16 weeks)

## Phase 0 — Design

Week 0:

```text
Glossary
Service boundaries and context map
Money representation ADR
Ledger model ADR (accounts, sign convention, holds)
Sync vs async communication ADR
Broker choice ADR
Transfer saga sequence diagram
```

## Phase 1 — Foundation

Weeks 1–3:

```text
Monorepo setup
fincore-common (config, logging, correlation ID)
identity-service: FastAPI, PostgreSQL, SQLAlchemy, Alembic
Users, registration, login
Password hashing
JWT (asymmetric) + JWKS
Refresh token rotation
Gateway (Nginx)
Docker Compose
Basic tests
CI skeleton
```

## Phase 2 — Core Ledger

Weeks 4–6:

```text
ledger-service
Wallets (ledger accounts) and system accounts
Postings and entries (append-only)
Balance projection
Row locking and lock ordering
Service-to-service authentication
Concurrency tests
```

## Phase 3 — Transfers and Distributed Consistency

Weeks 7–9:

```text
payment-service
Transfers + state machine
Public idempotency
Idempotent ledger postings
Saga orchestration
Timeouts and unknown outcomes
Recovery worker
Reconciliation job
```

This is the most important phase. It is never shortened.

## Phase 4 — Async Architecture

Weeks 10–11:

```text
Transactional outbox + relay
Kafka
Domain events and schemas
notification-service
Consumer idempotency
Retries, retry topics, DLT
Distributed tracing
```

## Phase 5 — Advanced Financial Features

Weeks 12–14:

```text
fraud-service (rule engine + failure policy)
Payments with holds, capture, refunds, expiration
webhook-service (signed delivery)
audit-service
Security improvements
```

## Phase 6 — Production Readiness

Weeks 15–16:

```text
Prometheus + Grafana
Full CI pipeline
E2E tests
Load testing
Documentation
Architecture diagrams
Deployment
```

If time runs short, reduce Webhooks or dashboards scope — never the ledger, idempotency or consistency work.

The roadmap may change if technical reasons justify it.

---

# 28. Git Strategy

Use clean Git history.

Example branches:

```text
main
develop

feature/identity-auth
feature/ledger-postings
feature/payment-transfers
feature/idempotency
feature/outbox
```

Use meaningful commits (Conventional Commits, scope = service or area).

Examples:

```text
feat(identity): implement user registration

feat(ledger): add wallet creation

feat(ledger): implement double-entry postings

feat(payment): add transfer saga orchestration

fix(payment): prevent duplicate transfer processing

test(ledger): add concurrent transfer integration tests

docs(adr): record money representation decision
```

---

# 29. GitHub Portfolio Quality

This project must eventually have a strong README containing:

```text
Project description
Architecture and service boundaries
Technology stack
Features
System diagram
Transfer saga sequence diagram
Database design per service
Event catalog
How to run locally
API documentation
Testing instructions
Important engineering decisions (links to ADRs)
Failure scenarios and how they are handled
Screenshots of Swagger/Grafana/Jaeger if useful
Roadmap
```

The repository should look like a serious engineering project rather than a tutorial repository.

---

# 30. Important Rules for You as My AI Mentor

When helping me with FinCore:

1. Do not generate the entire project at once.

2. Work step by step.

3. Before giving code, explain:

   * what we are building
   * why it is needed
   * how it works

4. I want to understand the code, not just copy it.

5. If I suggest a bad architecture decision, explain why instead of blindly implementing it.

6. Prefer production-oriented approaches but avoid unnecessary overengineering.

7. Do not introduce a technology just because it sounds impressive.

8. Keep financial consistency and security as top priorities.

9. When we create database models, explain relationships and constraints.

10. When we create APIs, explain request flow and response design.

11. When bugs happen, help me understand the root cause.

12. When giving terminal commands, explain important commands.

13. Keep the architecture consistent with previous decisions.

14. If a major architecture decision needs to change, explain the reason first.

15. Never use fake implementation shortcuts for critical financial logic.

16. Never put secrets, API keys, tokens, or passwords into source code.

17. Prefer realistic engineering practices.

18. Write code that could reasonably exist in a real backend project.

19. Keep service boundaries based on business capability and consistency. Never split data that must change atomically across services, never share databases between services, and never create a new service without a clear reason.

20. For every cross-service interaction, explain what happens on timeout, duplicate delivery, and partial failure.

21. Always keep the project goal in mind:

> Build one serious production-oriented backend project that helps me become a stronger Python Backend Developer.

---

# 31. Current Project State

When I start a fresh conversation and only provide this document, assume:

```text
Project: FinCore
Status: Starting from zero (Phase 0 — Design)
Architecture: Microservices (database-per-service, outbox, sagas)
Language: Python
Framework: FastAPI
Database: PostgreSQL (one database per service)
ORM: SQLAlchemy (async)
Migrations: Alembic
Broker: Kafka
Testing: pytest + testcontainers
Deployment environment: Docker
```

Do not begin coding immediately unless I specifically ask you to.

First understand the current phase and continue from there.

---

# 32. First Milestone

Our first milestone is:

```text
FinCore v0.1
```

It should include:

```text
Phase 0 ADRs and glossary
Monorepo structure
fincore-common (config, structured logging, correlation ID)
identity-service:
  FastAPI application
  Project configuration
  PostgreSQL connection
  Alembic migrations
  User model
  User registration
  Login
  Password hashing
  JWT access token (asymmetric) + JWKS endpoint
  Refresh token (hashed, rotated, reuse detection)
  GET /api/v1/users/me
Gateway (Nginx) routing to identity-service
Docker Compose setup
Basic tests
CI skeleton
README
```

Only after v0.1 is clean and tested should we move to ledger-service.

---

# 33. Revision Notes (v1 → v2)

Changes made to the original spec and why:

| # | Original | Problem | Fix |
|---|---|---|---|
| 1 | Modular monolith | Owner's decision: microservices, bank-like system | Microservices by business capability, database-per-service (Section 3) |
| 2 | "Commit → Publish domain event" | Dual-write: crash between commit and publish loses events; publishing before commit emits events for rolled-back operations | Transactional outbox (Section 14.1) |
| 3 | "Check balance" before "Open DB transaction" | TOCTOU race: two concurrent requests both see enough balance | Balance checked after row lock inside the ledger transaction (Sections 8.4, 10) |
| 4 | No lock ordering | A→B and B→A concurrently can deadlock | Lock accounts in ascending id order (Section 8.4) |
| 5 | Money format undefined | Risk of float rounding errors | BIGINT minor units, decimal strings in API (Section 6.1) |
| 6 | Currency mixing undefined | Cross-currency transfers need FX, rates, FX accounts | v1: same-currency only (Section 6.2) |
| 7 | Ledger had no counterpart accounts | Deposits/payments have no balancing side | System accounts, postings, append-only, reversals, holds, reconciliation (Section 8) |
| 8 | One Transaction table for all types | Nullable-column model does not fit deposits/payments; mixes intention and accounting | Business operations (payment-service) vs postings (ledger-service) (Section 7) |
| 9 | Idempotency underspecified | Concurrent duplicates, key reuse with different body, no scope/TTL | Per-user scope, fingerprint, IN_PROGRESS/COMPLETED, TTL, internal idempotency (Section 9) |
| 10 | Statuses without transitions | Invalid transitions (e.g., COMPLETED → PENDING) possible | Explicit state machines (Sections 7.3, 11) |
| 11 | — (new with microservices) | Network timeouts create unknown outcomes | Saga with idempotent retries, recovery worker, reconciliation (Section 10) |
| 12 | — (new with microservices) | Fraud-service outage blocks or bypasses risk checks | Configurable fail-open/fail-closed policy (Section 12) |
| 13 | — (new with microservices) | Internal APIs callable by anyone; tokens verified with shared secret | Asymmetric JWT + JWKS, service-to-service auth, internal endpoints hidden (Section 19) |
| 14 | Tracing as "later" | Debugging across services impossible without it | Correlation ID + OpenTelemetry required from Phase 4 (Section 24) |
| 15 | Refresh tokens storage unspecified | Plain tokens in DB are a breach risk | Hashed storage + reuse detection (Section 5) |
| 16 | Tests environment unspecified | Locking/concurrency behavior differs outside PostgreSQL | Real PostgreSQL via testcontainers; contract and saga failure tests (Section 23) |
| 17 | 10–12 week roadmap | Too tight, especially the financial core | 16-week roadmap with Phase 0 design (Section 27) |

---

# Final Context

FinCore is my main flagship GitHub backend project.

The objective is not to finish as quickly as possible.

The objective is to use this project to deeply learn:

```text
Backend Architecture
Microservices and Service Boundaries
FastAPI
PostgreSQL
Database Design
Transactions
Financial Systems and Double-Entry Ledgers
Concurrency
Idempotency
Sagas and Distributed Consistency
Transactional Outbox
Redis
Kafka
Distributed Systems
Security
Testing
Docker
CI/CD
Monitoring and Tracing
Production Engineering
```

Whenever helping me, optimize for **learning + engineering quality + realistic backend development**, not maximum code generation speed.

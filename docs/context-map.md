# FinCore — Context Map

This document maps the bounded contexts (services) in FinCore, how they
depend on each other, and — critically — what kind of integration connects
them. It is the reference point every later ADR and saga diagram builds on.

See [glossary.md](glossary.md) for term definitions and Section 3 of
[spec.md](spec.md) for the full architecture rationale.

---

## 1. Bounded contexts

| Context | Service | Owns | Consistency boundary |
|---|---|---|---|
| Authentication, Users, RBAC | `identity-service` | users, roles, sessions, refresh tokens | Independent — no other service needs strong consistency with it |
| Wallets, Ledger, Balances | `ledger-service` | ledger accounts, postings, entries, balances, holds | **Core.** Wallet balance and its entries must always be consistent — they never split across services |
| Transfers, Payments, Refunds, Merchants | `payment-service` | transfers, payments, refunds, merchants, idempotency keys | Owns the saga; consistent with itself only, treats ledger and fraud as external |
| Fraud / Risk | `fraud-service` | fraud checks, rule configs, counters | Independent, stateless decision service |
| Notifications | `notification-service` | notifications, delivery attempts | Independent, purely reactive |
| Webhooks | `webhook-service` | endpoints, deliveries, attempts | Independent, purely reactive |
| Audit Logs | `audit-service` | append-only audit records | Independent, purely reactive |

`gateway` is not a bounded context — it owns no data and no business rules,
only routing and cross-cutting concerns (TLS, rate limiting, correlation
ID).

---

## 2. Relationships

For each pair of contexts that communicate, this table states the
integration type and who depends on whom.

| Upstream | Downstream | Type | Why |
|---|---|---|---|
| `identity-service` | all other services | **Async (implicit) via JWT + JWKS** | Every service verifies JWTs locally using identity's public key. No per-request call to `identity-service`. |
| `identity-service` | `audit-service` | Async (event) | `user.registered`, `user.blocked` are audited. |
| `payment-service` | `ledger-service` | **Sync (internal REST)** | The saga cannot proceed without knowing whether a posting succeeded, failed, or is unknown (timeout). |
| `payment-service` | `fraud-service` | **Sync (internal REST, timeout)** | A transfer/payment cannot proceed to the ledger step without a risk decision. |
| `ledger-service` | `payment-service` | Async (event) | `ledger.posting.completed` lets payment-service confirm outcomes independently of the synchronous call's success (recovery path). |
| `payment-service` | `notification-service`, `webhook-service`, `audit-service` | Async (event) | `transfer.completed`, `payment.completed`, etc. — pure reactions, no answer needed. |
| `fraud-service` | `audit-service` | Async (event) | `fraud.detected`, `fraud.review_required` are audited. |

**Rule of thumb** (Section 3.1.4 of the spec): synchronous when the caller
needs an answer to continue its own transaction; asynchronous when the
other side only needs to react. This rule is formalized in
[ADR-0003](adr/0003-sync-vs-async-communication.md).

---

## 3. Why `ledger-service` has no upstream dependency

`ledger-service` never calls `payment-service`, `fraud-service`, or any
other service synchronously. It is a pure accounting engine: it accepts
balanced postings and holds, and rejects anything that violates ledger
invariants. It does not know *why* a posting was requested (transfer vs.
payment vs. refund) — that intention lives entirely in `payment-service`.

This makes `ledger-service` the most stable, most protected context in the
system: nothing it depends on can make it unavailable, and its API surface
never has to change when payment logic changes.

---

## 4. Diagram

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

(Identical to Section 3.3 of the spec — reproduced here so the context map
is self-contained.)

---

## 5. Anti-corruption notes

* No service stores a copy of another service's domain model. Where a
  service needs a fact it doesn't own (e.g. user status), it reads it from
  a JWT claim, an internal API call, or a domain event — never a shared
  table or a cross-database join.
* `payment-service` treats `ledger-service` as an opaque posting engine; it
  never reaches into ledger internals (account kinds, sign convention) —
  it only sends amount + currency + source/destination account references
  and interprets the result (success / business rejection / unknown).
* `fraud-service` receives only the facts it needs to score a request
  (amount, user id, device/IP signals) — never full user profiles or
  wallet balances.

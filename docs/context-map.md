# FinCore — Context Map

This document maps the bounded contexts (services) in FinCore, how they
depend on each other, and — critically — what kind of integration connects
them. It is the reference point every ADR and diagram builds on.

It describes the system **as built**. Integrations that were designed in
Phase 0 but not yet implemented are kept, marked *planned*, so the gap
between target design (Section 3 of [spec.md](spec.md)) and reality stays
visible instead of silently disappearing.

See [glossary.md](glossary.md) for term definitions and
[diagrams/architecture.md](diagrams/architecture.md) for the diagrams.

---

## 1. Bounded contexts

| Context | Service | Owns (database) | Consistency boundary |
|---|---|---|---|
| Authentication, Users, RBAC | `identity-service` | users, roles, sessions, refresh tokens (`identity_db`) | Independent — no other service needs strong consistency with it |
| Wallets, Ledger, Balances | `ledger-service` | ledger accounts, postings, entries, balances, holds (`ledger_db`) | **Core.** Wallet balance and its entries must always be consistent — they never split across services |
| Transfers, Payments, Refunds, Merchants | `payment-service` | transfers, payments, refunds, merchants, idempotency keys, outbox (`payment_db`) | Owns the sagas; consistent with itself only, treats ledger and fraud as external |
| Fraud / Risk | `fraud-service` | fraud checks with their scores and triggered rules (`fraud_db`); rules live in code, thresholds in config | Independent decision service; its own check history feeds its frequency rules |
| Notifications | `notification-service` | notifications, dead letters (`notification_db`) | Independent, purely reactive |
| Webhooks | `webhook-service` | endpoints, deliveries, attempts (`webhook_db`) | Independent, reactive, plus its own registration API |
| Audit Logs | `audit-service` | append-only audit logs, dead letters (`audit_db`) | Independent, purely reactive; append-only enforced by database privileges |

`gateway` is not a bounded context — it owns no data and no business rules,
only routing and cross-cutting concerns (auth-endpoint rate limiting,
request size limits, correlation ID). It routes public `/api/v1/*` paths
only; `/internal/*` and `/metrics` have no route through it at all.

---

## 2. Relationships

For each pair of contexts that communicate, this table states the
integration type, who depends on whom, and whether it exists today.

| Upstream | Downstream | Type | Status | Why |
|---|---|---|---|---|
| `identity-service` | all services with a public API | JWT verified locally via published JWKS | Built | No per-request call to `identity-service` (ADR-0003). |
| `payment-service` | `ledger-service` | **Sync (internal REST)**: postings, holds, capture, release, system accounts | Built | The saga can't proceed without knowing whether a posting succeeded, failed, or is unknown (timeout). The recovery worker resolves an unknown outcome by re-sending the same call with the same `source_id` — idempotent on ledger's side, which returns the existing posting or hold if the first attempt did land. |
| `payment-service` | `ledger-service` | **Sync (public REST, caller's own JWT)**: `GET /api/v1/wallets/{id}` | Built | Wallet-ownership check reuses ledger's own authorization instead of duplicating it. |
| `payment-service` | `fraud-service` | **Sync (internal REST, timeout + fail-open/closed policy)** | Built | A transfer/payment can't reach the ledger step without a risk decision. |
| `webhook-service` | `payment-service` | **Sync (internal REST)**: `GET /internal/v1/merchants/{id}` | Built | Verifies merchant ownership when an endpoint is registered; webhook-service has no merchants table of its own. |
| `payment-service` | `notification-service` | Async — `transfers` topic | Built | `transfer.completed` / `transfer.failed` — pure reactions. |
| `payment-service` | `webhook-service` | Async — `payments` topic | Built | `payment.completed` / `failed` / `refunded` fan out to merchant endpoints. |
| `payment-service` | `audit-service` | Async — `transfers` and `payments` topics | Built | Every published event becomes an audit record. |
| `identity-service` | `audit-service` | Async — `users` topic: `user.registered`, `user.login`, `user.password_changed`, `user.blocked`, `user.suspended`, `user.reactivated`, `user.role_granted`, `user.role_revoked` | Built | Account changes are audited (spec Section 18: USER_BLOCKED, admin actions). Written through identity-service's own outbox in the same transaction as the change; its relay retries until Kafka is reachable, so login never depends on the broker. |
| `ledger-service` | `payment-service` | Async (event) — `ledger.posting.completed` | *Planned* | Designed as a second recovery path; today recovery re-sends the idempotent call above, and ledger-service publishes no events. |
| `fraud-service` | `audit-service` | Async — `fraud` topic: `fraud.detected` (BLOCK), `fraud.review_required` (REVIEW) | Built | Risk decisions are audited under the operation they were about. Written through fraud-service's own outbox with the `fraud_checks` row; ALLOW publishes nothing. The relay retries until Kafka is reachable, so scoring never waits on it. |

Every event and every internal API above is covered by a committed
contract (`contracts/events/`, `contracts/openapi/`) enforced from both
the producer's and the consumer's side — see the README's "Contract
tests".

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

See [diagrams/architecture.md](diagrams/architecture.md) for the system as
built — services, databases, topics and observability. Section 3.3 of the
spec shows the original target design, including the planned integrations
above and Redis, which hasn't been introduced (nothing needs it yet, per
the project's rule against speculative infrastructure).

---

## 5. Anti-corruption notes

* No service stores a copy of another service's domain model. Where a
  service needs a fact it doesn't own (e.g. user status, merchant owner),
  it reads it from a JWT claim, an internal API call, or a domain event —
  never a shared table or a cross-database join. webhook-service keeps the
  merchant's owner id captured at registration time, a fact that doesn't
  change in this system — not a copy of the merchant.
* `payment-service` treats `ledger-service` as an opaque posting engine; it
  never reaches into ledger internals (account kinds, sign convention) —
  it only sends amounts, currency and account references, and interprets
  the result (success / business rejection / unknown).
* `fraud-service` receives only the facts it needs to score a request
  (user id, amount, currency, operation type and id) — never user
  profiles or wallet balances. Device and IP signals aren't sent because
  nothing captures them yet, which is why the spec's "new device" and
  "suspicious IP" rules aren't implemented.

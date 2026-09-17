# FinCore

A digital wallet and payment platform built as a microservices system, in
the style of a real core-banking backend: database-per-service,
double-entry ledger, sagas for distributed consistency, transactional
outbox, and asymmetric-JWT auth with JWKS.

This is a learning-driven, production-oriented portfolio project — not a
tutorial. Every non-obvious decision is recorded as an [ADR](docs/adr/)
rather than left implicit, and the full design rationale lives in
[`docs/spec.md`](docs/spec.md).

**Status: Phase 2 (Core Ledger) complete.** `identity-service` and
`ledger-service` are built, tested, and run together via Docker Compose.
Payments, fraud, notifications, webhooks, and audit are designed (see the
ADRs and [`docs/context-map.md`](docs/context-map.md)) but not yet built.
The table in [Roadmap](#roadmap) below tracks this precisely — nothing
here is described as done unless it's tested and running.

---

## Architecture

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
```

Bold rule underlying every service boundary: **a service owns its API,
its logic, and its data — no cross-service database access, no shared
domain models.** Data that must change atomically (a wallet balance and
its ledger entries) stays inside one service rather than being split
across a distributed transaction. The full reasoning is in
[`docs/context-map.md`](docs/context-map.md) and Section 3 of the spec.

### Why services are split this way

| Service | Owns | Why it's separate |
|---|---|---|
| `identity-service` ✅ | users, roles, sessions, refresh tokens | Different security/scaling profile from money movement |
| `ledger-service` ✅ | ledger accounts, postings, entries, balances, holds | Core banking; accepts balanced postings only, knows nothing about *why* — this is what keeps it the most stable service in the system |
| `payment-service` | transfers, payments, refunds, idempotency keys | Owns the saga; transfers/payments/refunds share the same orchestration machinery, so splitting them would duplicate it |
| `fraud-service` | fraud checks, rules | Isolated so the rule engine can become an ML model later without touching payment logic |
| `notification-service` / `webhook-service` / `audit-service` | their own event tables | Pure asynchronous event consumers — the natural boundary for "reacts, doesn't decide" |

✅ = implemented. Everything else is designed (ADRs + context map) and
scheduled per the [roadmap](#roadmap).

---

## Tech stack

```text
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic
PostgreSQL (one database, one least-privilege role, per service)
Nginx (gateway), Docker / Docker Compose
pytest + pytest-asyncio + testcontainers (real PostgreSQL in tests, never SQLite)
ruff + mypy
GitHub Actions
```

Planned, not yet introduced (added when the roadmap reaches them, per the
project's own rule against speculative infrastructure): Kafka, Redis,
OpenTelemetry, Prometheus/Grafana.

---

## What's implemented

### `identity-service`

Authentication, users, and RBAC — spec Sections 5 and 19.

* `POST /api/v1/auth/register` — email/phone uniqueness enforced at both
  the service layer (fast, friendly error) and the database's UNIQUE
  constraint (the actual race-safe guard — see
  [ADR-0002](docs/adr/0002-ledger-model.md)'s "let the database decide"
  pattern, applied here to registration).
* `POST /api/v1/auth/login` — Argon2id password verification, issues an
  access token + refresh token.
* `POST /api/v1/auth/refresh` — refresh token rotation. Redeeming a token
  is an atomic `UPDATE ... WHERE used_at IS NULL`, so two concurrent
  redemptions of the same token can't both succeed silently. Reusing an
  already-rotated token — replay or a lost race — revokes the entire
  session family.
* `POST /api/v1/auth/logout` — idempotent.
* `GET /api/v1/users/me` — protected by a bearer-token dependency.
* `GET /.well-known/jwks.json` — publishes the Ed25519 public key so any
  service can verify a FinCore JWT locally, without calling back into
  identity-service per request.
* `GET /health`, `GET /ready` — liveness and DB-readiness checks.

Passwords: Argon2id. Refresh tokens: stored only as a SHA-256 hash
(a fast hash is deliberate — the token is 256 bits of randomness, not a
low-entropy password; see the comment in `app/domain/session.py`). JWTs:
Ed25519 (EdDSA), asymmetric, short-lived (15 min default).

**Database:**

```text
identity_db: users, roles, user_roles, sessions, refresh_tokens
```

`roles` is seeded with `USER` / `SUPPORT` / `ADMIN` by its own migration.

### `ledger-service`

Wallets, double-entry postings, balances, and holds — the source of truth
for money (ADR-0002, spec Section 8).

* `POST /api/v1/wallets`, `GET /api/v1/wallets`, `GET /api/v1/wallets/{id}`,
  `GET /api/v1/wallets/{id}/entries` — protected by a bearer token that
  `ledger-service` verifies **entirely on its own**, using
  identity-service's JWKS endpoint (cached in memory, not fetched per
  request). No network call to identity-service on the hot path.
* `POST /internal/v1/postings`, `GET /internal/v1/postings/{source_id}` —
  the engine payment-service (Phase 3) will call to move money, and the
  endpoint its recovery worker will use to resolve a timed-out call's
  real outcome. Never routed through the gateway; requires the shared
  `X-Internal-Token` header (Section 19 — mTLS is a later concern).
* `POST /internal/v1/holds`, `.../{id}/capture`, `.../{id}/release` — the
  reserve → capture/release flow for merchant payments. A hold changes
  only `held_minor`, no posting; only a capture moves real money, into
  the currency's `MERCHANT_SETTLEMENT` account.

Every posting (transfer, deposit, payment capture — anything that moves
money) goes through one function, `create_posting()`, which:

1. Checks idempotency first — `(source_service, source_id, type)` is
   unique, so a retry returns the existing posting untouched.
2. Validates `debits == credits` before taking any lock.
3. Locks every account's balance with `SELECT ... FOR UPDATE`, **one at a
   time, in ascending account_id order** — not one multi-row query,
   because PostgreSQL doesn't guarantee a single query's row-locking
   order follows `ORDER BY`. This is what lets two transfers between the
   same two wallets, in opposite directions, run concurrently without
   deadlocking each other (verified by an actual `asyncio.gather` test,
   not just reasoned about).
4. Only *after* the lock: checks currency, `ACTIVE` status, and — for
   `USER_WALLET` accounts — that available balance won't go negative.
   This ordering is the TOCTOU fix from the spec's own revision notes.
5. Inserts the posting + entries (both append-only) and applies the
   balance deltas, in one commit.

**Database:**

```text
ledger_db: ledger_accounts, postings, ledger_entries, account_balances, holds
```

`ledger_accounts` is seeded with one system account per
`(kind, currency)` — `EXTERNAL_FUNDING`, `EXTERNAL_PAYOUT`,
`MERCHANT_SETTLEMENT`, `FEES`, `SUSPENSE` × `UZS`/`USD` — by its own
migration, alongside `account_balances` rows so every account has a
balance from the moment it exists. Two partial unique indexes (not one
plain `UNIQUE`) enforce "one wallet per user per currency" and "one
system account per kind per currency" simultaneously — a single
constraint can't do both, because SQL treats every `NULL` `owner_user_id`
as distinct.

Every migration in both services is verified with a real
`upgrade → downgrade → upgrade` cycle before being committed. This caught
two real bugs: PostgreSQL native enum types aren't dropped by
`drop_table()` (identity-service's first migration originally left
`user_status` behind), and reusing a native enum type across two tables'
columns requires the dialect-specific `postgresql.ENUM(create_type=False)`
— the generic `sqlalchemy.Enum(create_type=False)` silently ignores the
flag and fails with "type already exists." Both are now covered by
regression tests in `tests/integration/test_migrations.py` in each
service.

---

## Run it

### Docker Compose (the whole stack)

```bash
cp services/identity-service/.env.example services/identity-service/.env
# then edit JWT_PRIVATE_KEY in that .env — generate one with:
openssl genpkey -algorithm ed25519

cp services/ledger-service/.env.example services/ledger-service/.env
# then edit INTERNAL_SERVICE_TOKEN in that .env to any random local value

docker compose up --build
```

| Via gateway | Direct |
|---|---|
| `http://localhost:8180` | `http://localhost:8091` (identity-service), `http://localhost:8092` (ledger-service) |

Swagger UI (FastAPI's auto-generated API docs):
`http://localhost:8091/docs` and `http://localhost:8092/docs`.

`/internal/*` routes (postings, holds) are deliberately **not** reachable
through the gateway (`8180`) — only directly against `ledger-service`
(`8092`, or by its service name from inside the Docker network), matching
Section 19. Verified: `curl -X POST localhost:8180/internal/v1/postings`
returns `404`; the same path against `localhost:8092` reaches the route
(and then rejects a missing/wrong `X-Internal-Token`).

> `docker-compose.yml`'s host ports (`8180`/`8091`/`8092`/`5440` instead
> of the more usual `8080`/`8001`/`8002`/`5432`) were picked to avoid
> clashing with other local projects on this dev machine — the internal
> container ports are unaffected. Change the left side of each
> `"host:container"` mapping in `docker-compose.yml` if these also
> collide with something on your machine.

### Running a service directly (faster edit/test loop)

```bash
cd libs/fincore-common && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"

cd ../../services/identity-service
python3.12 -m venv .venv
.venv/bin/pip install -e ../../libs/fincore-common
.venv/bin/pip install -e ".[dev]"

cp .env.example .env   # fill in DATABASE_URL and JWT_PRIVATE_KEY

# Postgres for local dev (change the host-side "5432:" if that port is
# already taken on your machine):
docker run --rm -d --name fincore-identity-dev \
  -e POSTGRES_USER=identity -e POSTGRES_PASSWORD=identity -e POSTGRES_DB=identity_db \
  -p 5432:5432 postgres:16-alpine

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

`ledger-service` the same way, in its own terminal — it also needs
`IDENTITY_SERVICE_JWKS_URL` pointing at a running identity-service:

```bash
cd services/ledger-service
python3.12 -m venv .venv
.venv/bin/pip install -e ../../libs/fincore-common
.venv/bin/pip install -e ".[dev]"

cp .env.example .env   # fill in DATABASE_URL, IDENTITY_SERVICE_JWKS_URL, INTERNAL_SERVICE_TOKEN

docker run --rm -d --name fincore-ledger-dev \
  -e POSTGRES_USER=ledger -e POSTGRES_PASSWORD=ledger -e POSTGRES_DB=ledger_db \
  -p 5433:5432 postgres:16-alpine

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8001
```

---

## Testing

```bash
cd libs/fincore-common && .venv/bin/pytest -v      # 32 tests
cd services/identity-service && .venv/bin/pytest -v # 52 tests
cd services/ledger-service && .venv/bin/pytest -v   # 48 tests
```

Integration tests spin up a real PostgreSQL container via `testcontainers`
— concurrency and locking behavior is never trustworthy on SQLite, so it's
never used here (spec Section 23). Several tests exercise real
concurrency, not just sequential behavior, using `asyncio.gather` to race
requests against each other and asserting that the *database* — not
application code timing — decides the winner:

* `test_concurrent_registration_with_the_same_email_rejects_one` and
  `test_concurrent_redemption_of_the_same_token_lets_only_one_succeed`
  (identity-service)
* `test_opposite_direction_transfers_between_the_same_two_wallets_do_not_deadlock`
  — two transfers, A→B and B→A, run concurrently with a timeout as a
  trip-wire; both complete, neither deadlocks
* `test_concurrent_capture_and_release_on_the_same_hold_resolve_to_exactly_one_outcome`
  (both in ledger-service)

```bash
cd services/identity-service && .venv/bin/ruff check . && .venv/bin/mypy app
cd services/ledger-service && .venv/bin/ruff check . && .venv/bin/mypy app
```

CI (`.github/workflows/ci.yml`) runs all of the above per package on every
push/PR.

---

## Engineering decisions

Recorded as ADRs rather than left implicit — each one explains the
problem, the decision, and what was rejected and why:

* [ADR-0001](docs/adr/0001-money-representation.md) — money as integer
  minor units, never `float`, decimal strings at the API boundary.
* [ADR-0002](docs/adr/0002-ledger-model.md) — double-entry ledger account
  kinds, debit/credit sign convention, holds.
* [ADR-0003](docs/adr/0003-sync-vs-async-communication.md) — when a
  cross-service call is synchronous vs. an event, and what every
  synchronous call does on timeout/duplicate/partial failure.
* [ADR-0004](docs/adr/0004-broker-choice.md) — Kafka over RabbitMQ, and
  why.
* [ADR-0005](docs/adr/0005-frontend-addition.md) — adding a React
  frontend, built after the backend core, and why not sooner.

Plus [`docs/glossary.md`](docs/glossary.md) (shared vocabulary),
[`docs/context-map.md`](docs/context-map.md) (service boundaries and
integration types), and
[`docs/diagrams/transfer-saga.md`](docs/diagrams/transfer-saga.md) (the
transfer saga sequence diagram, including its failure branches — designed
ahead of `payment-service`'s implementation in Phase 3).

---

## Failure scenarios handled today

| Scenario | Behavior |
|---|---|
| Two requests register the same email concurrently | Exactly one succeeds — the database's UNIQUE constraint decides, not a pre-check race (verified by test, not just asserted) |
| Two requests redeem the same refresh token concurrently | Exactly one succeeds; the atomic `UPDATE ... WHERE used_at IS NULL` decides |
| A refresh token is replayed after rotation | The entire session is revoked immediately — every token in that family stops working |
| Database is unreachable | `/ready` returns `503`, not a bare 500 or a hang |
| A bearer token is missing, malformed, expired, wrong-issuer, or belongs to a blocked user | `401` with a consistent RFC 7807 body (`{"type", "title", "status", "detail", "instance"}`) — the same shape for every error, in every service, via `fincore-common`'s `DomainError` |
| Login/register are hit with a burst of requests | Nginx rate-limits them (10r/s, burst 20) before they reach identity-service at all |
| A posting's debits don't equal its credits | Rejected before any lock is taken — `422 Unbalanced Posting` |
| Two transfers move money between the same two wallets in opposite directions, concurrently | Both complete correctly; locks are acquired one account at a time in ascending `account_id` order, so neither transaction can be waiting on a lock the other already holds |
| A transfer would take a wallet's available balance negative | Rejected *after* the row lock, inside the same transaction — never before it (the TOCTOU fix from the spec's revision notes) — `409 Insufficient Funds` |
| The same posting is submitted twice (retry after a timeout) | The second call returns the *existing* posting; money moves exactly once |
| A hold is captured for less than the full held amount | The remainder is released, not left as a smaller open hold |
| A hold is captured twice (retry) | Idempotent — the existing posting is returned, money doesn't move twice |
| Capture and release are called concurrently for the *same* hold | The hold row's own lock serializes them; exactly one resolves it, the other sees the result and takes its idempotent path |
| A capture is attempted on an expired hold | The hold is released as a side effect and the capture is rejected — `409 Hold Expired` |
| `/internal/*` endpoints are called without a service token, or through the gateway | Missing token → `422`; wrong token → `403`; through the gateway → `404` (no route exists there at all) |

Saga-level failure handling (a ledger call timing out mid-transfer, an
"unknown outcome," recovery workers, reconciliation) is designed in
[ADR-0003](docs/adr/0003-sync-vs-async-communication.md) and the
[transfer saga diagram](docs/diagrams/transfer-saga.md), and will move
into this table once `payment-service` exists (Phase 3) — the ledger side
of that flow (the `POST /internal/v1/postings` call it makes) is already
built and covered above.

---

## Roadmap

Full detail in `docs/spec.md` Section 27. Status here is updated as
phases complete — not aspirational.

| Phase | Weeks | Scope | Status |
|---|---|---|---|
| 0 — Design | 0 | Glossary, context map, ADRs, saga diagram | ✅ |
| 1 — Foundation | 1–3 | `fincore-common`, `identity-service`, gateway, Docker Compose, CI | ✅ |
| 2 — Core Ledger | 4–6 | `ledger-service`, postings, holds, row locking | ✅ |
| 3 — Transfers & Distributed Consistency | 7–9 | `payment-service`, sagas, idempotency, recovery worker | ⏳ |
| 4 — Async Architecture | 10–11 | Transactional outbox, Kafka, `notification-service`, tracing | ⏳ |
| 5 — Advanced Financial Features | 12–14 | `fraud-service`, payment holds/refunds, `webhook-service`, `audit-service` | ⏳ |
| 6 — Production Readiness | 15–16 | Prometheus/Grafana, full CI, e2e, load testing | ⏳ |
| 7 — Frontend | after 6 | React/TypeScript dashboard + admin panel ([ADR-0005](docs/adr/0005-frontend-addition.md)) | ⏳ |

Per the spec's own rule: if time runs short, webhook/dashboard scope
shrinks first — the ledger, idempotency, and consistency work is never
shortened.

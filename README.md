# FinCore

A digital wallet and payment platform built as a microservices system, in
the style of a real core-banking backend: database-per-service,
double-entry ledger, sagas for distributed consistency, transactional
outbox, and asymmetric-JWT auth with JWKS.

This is a learning-driven, production-oriented portfolio project — not a
tutorial. Every non-obvious decision is recorded as an [ADR](docs/adr/)
rather than left implicit, and the full design rationale lives in
[`docs/spec.md`](docs/spec.md).

**Status: Phase 4 (Async Architecture) complete.** `identity-service`,
`ledger-service`, `payment-service`, and `notification-service` are
built, tested, and run together via Docker Compose — gateway, Kafka, and
Jaeger included. Fraud (the real service), webhooks, and audit are
designed (see the ADRs and [`docs/context-map.md`](docs/context-map.md))
but not yet built. The table in [Roadmap](#roadmap) below tracks this
precisely — nothing here is described as done unless it's tested and
running.

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
| `payment-service` ✅ | transfers, payments, refunds, idempotency keys, the outbox | Owns the saga; transfers/payments/refunds share the same orchestration machinery, so splitting them would duplicate it |
| `notification-service` ✅ | notifications, retry/DLT state | Pure asynchronous event consumer — the natural boundary for "reacts, doesn't decide" |
| `fraud-service` ✅ | fraud checks, rules | Isolated so the rule engine can become an ML model later without touching payment logic |
| `webhook-service` / `audit-service` | their own event tables | Same "reacts, doesn't decide" boundary as `notification-service` |

✅ = implemented. Everything else is designed (ADRs + context map) and
scheduled per the [roadmap](#roadmap).

---

## Tech stack

```text
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic
PostgreSQL (one database, one least-privilege role, per service)
Kafka (KRaft mode — no Zookeeper), aiokafka
OpenTelemetry (traces) + Jaeger, structured JSON logging
Nginx (gateway), Docker / Docker Compose
pytest + pytest-asyncio + testcontainers (real PostgreSQL/Kafka in tests, never SQLite or fakes)
ruff + mypy
GitHub Actions
```

Planned, not yet introduced (added when the roadmap reaches them, per the
project's own rule against speculative infrastructure): Redis,
Prometheus/Grafana.

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
  the endpoint `payment-service` calls to move money, and the one its
  recovery worker uses to resolve a timed-out call's real outcome. Never
  routed through the gateway; requires the shared `X-Internal-Token`
  header (Section 19 — mTLS is a later concern).
* `POST /internal/v1/holds`, `.../{id}/capture`, `.../{id}/release` — the
  reserve → capture/release flow for merchant payments (not yet called by
  anything — `payment-service` only does direct transfers so far; holds
  are exercised today by ledger-service's own tests, and will back
  Phase 5's payment-capture flow).
* `GET /internal/v1/reconciliation` — triggers one reconciliation pass on
  demand, on top of the background job described below.

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

A background **reconciliation job** (spec Section 8.4, ADR-0002) runs
every `RECONCILIATION_INTERVAL_SECONDS` (default 300s) and independently
re-derives every invariant the ledger promises — straight from the
append-only entry log, never trusting the denormalized
`account_balances` cache it exists to check: every posting balanced,
each account's balance equal to the signed sum of its entries, no
wallet's available balance negative, no duplicate posting per
`source_id`. A violation is logged as an incident and never
auto-corrected — reconciliation detects, it doesn't fix.

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

### `payment-service`

Transfers, idempotency, and the distributed transaction — spec Sections
9, 10, and 20.

* `POST /api/v1/transfers` — the flow runs in this exact order:
  authorize (does the source wallet belong to the caller — relayed to
  `ledger-service`'s own public wallet endpoint rather than duplicating
  that check) → validate (same-wallet, currency match, amount) →
  idempotency check → create the `Transfer` and run its saga.
* `GET /api/v1/transfers/{id}` — owner-only; "doesn't exist" and "exists
  but isn't yours" return the same `404`.
* `GET /api/v1/transactions`, `GET /api/v1/transactions/{id}` — a
  type-erased view over the caller's own business operations (`Transfer`
  today; a future `Payment` would join the same list without changing
  its shape).

**The saga** (`app/services/transfers.py`), per spec Section 10.1:

```text
fraud BLOCK               → FAILED, ledger never called
fraud REVIEW               → stays PENDING
fraud service unreachable  → fail-open/fail-closed policy decides
                              (amount ≤ threshold → ALLOW+flagged,
                               amount > threshold → REVIEW)
ledger posting succeeds     → COMPLETED
ledger business rejection   → FAILED (e.g. insufficient funds)
ledger unreachable/timeout  → stays PROCESSING — an unknown outcome is
                               never reported as a failure, because the
                               money may or may not have actually moved
```

Every status transition is an atomic `UPDATE ... WHERE status =
:expected` (`TransferRepository.transition_status`) — the state machine
is enforced by the database update itself, never assumed from
in-memory state.

**Public API idempotency** (`Idempotency-Key` header, spec Section 9.1):
a SHA-256 fingerprint of method + path + canonicalized JSON body is
stored alongside the key, so retrying the *same* request replays the
original response verbatim, while reusing the key for a *different*
request is rejected with `422`. The `UNIQUE(user_id, key)` constraint —
not the pre-check — is what actually decides a race between two
concurrent first-time requests carrying the same key.

**The recovery worker** (`app/services/recovery.py`) runs in the
background every `RECOVERY_WORKER_INTERVAL_SECONDS` (default 30s) and
retries the ledger posting for any transfer that's been stuck
`PROCESSING` for more than `RECOVERY_WORKER_STUCK_AFTER_SECONDS` (default
60s). Retrying is safe: `ledger-service`'s posting endpoint is idempotent
on `(source_service, source_id, type)`, so a retry of a posting that
already succeeded just returns the existing one instead of moving money
twice.

**The transactional outbox** (`app/domain/outbox.py`, spec Section
14.1): every time the saga transitions a transfer to `COMPLETED` or
`FAILED`, an `outbox_events` row is written in the *same* database
transaction as that status change — so a committed transition can never
silently fail to get an event. A background relay
(`app/services/outbox.py`) publishes unpublished rows to Kafka's
`transfers` topic every `OUTBOX_RELAY_INTERVAL_SECONDS` (default 5s),
keyed by transfer id for per-transfer ordering, and marks each published
only *after* a successful send. A race the outbox design doesn't
prevent on its own — the recovery worker retrying a transfer the
original saga call is still mid-flight on — is closed by only letting
whichever caller's `transition_status()` UPDATE actually applied write
the outbox event (verified with a real `asyncio.gather` race against
Postgres, not just reasoned about).

**Database:**

```text
payment_db: idempotency_keys, transfers, outbox_events
```

### `notification-service`

Consumes domain events and dispatches (mocked) notifications — spec
Sections 15 and 16. A pure event consumer: no public API beyond
`/health` and `/ready`, not routed through the gateway.

* Consumes `transfer.completed` / `transfer.failed` from the `transfers`
  topic and dispatches each through three logging-mock channels
  (`app/services/providers.py` — Email/SMS/Push behind one interface, so
  a real provider can replace a mock later without touching the
  consumer). No paid external provider is required for v1, per spec.
* **Consumer idempotency**: `notifications.event_id` is `UNIQUE` and
  doubles as the guard — a redelivered event (the normal consequence of
  Kafka's at-least-once delivery) is a no-op, not a second notification.
* **Retry topics + dead-letter queue** (`app/services/dispatch.py`, spec
  Section 16): a failed event is classified, not just retried in place —
  blocking the original partition until one poison message succeeds
  would stall every other message queued behind it.

  ```text
  permanent error (bad data)                -> DLT immediately
  transient error (e.g. provider timeout),
    attempts remaining                       -> "transfers-retry" topic, delayed
  transient error, attempts exhausted        -> DLT
  ```

  Retry state (attempt count, not-before time, last error) rides inside
  a second `EventEnvelope` on its own topic rather than a new wire
  format. Exponential backoff with jitter
  (`RetryPolicy.delay_seconds`) avoids a burst of simultaneously-failing
  messages retrying in lockstep. A dedicated retry-topic consumer (its
  own consumer group) waits out each message's remaining backoff and
  re-attempts it — delaying only that topic's own partition, never the
  main one.
* Dead-lettered events land on a `transfers-dlt` topic and in a
  queryable `dead_letters` table, with a manual-replay internal API
  (`GET`/`POST /internal/v1/dead-letters[/{id}/replay]`,
  token-authenticated like every other `/internal/*` endpoint) that
  republishes the original event onto the main topic for ordinary
  reprocessing.

**Database:**

```text
notification_db: notifications, dead_letters
```

### `fraud-service`

A rule-based risk engine (spec Section 12) — `payment-service`'s
transfer saga calls it synchronously on every transfer, and its
fail-open/fail-closed policy (`app/services/fraud.py` in
`payment-service`) was designed and tested against this service being
genuinely unreachable *before* it existed; that failure path is now
exercised by the real thing instead of only a fake transport.

* `POST /internal/v1/risk-checks` — scores an operation, persists the
  result, and returns a decision. Idempotent on
  `(operation_id, operation_type)`: a retried check for the same
  operation returns the stored result instead of re-scoring, which also
  keeps the frequency-based rules below from double-counting a retry as
  a second operation.
* Three rules (`app/services/rules.py`, spec Section 12's Strategy
  pattern — each rule is independent and contributes a fixed weight if
  triggered):

  ```text
  LARGE_AMOUNT       amount > threshold                          +30
  HIGH_FREQUENCY     ≥ N risk checks for this user in the window  +25
  REPEATED_FAILURES  ≥ N REVIEW/BLOCK decisions for this user     +25

  score 0-39  -> ALLOW
  score 40-69 -> REVIEW
  score 70+   -> BLOCK
  ```

  Two of spec Section 12's example rules — "new device" and "suspicious
  IP" — are deliberately not implemented: nothing in FinCore captures a
  device fingerprint anywhere, and `payment-service`'s risk-check
  request doesn't carry the caller's IP. Faking those signals from data
  that doesn't exist would be worse than not having them; the `Rule`
  interface is exactly what lets them be added later as real rules once
  that data actually exists.
* Every check is stored with its score and which rules fired
  (`fraud_checks.rules_triggered`), per spec Section 12 — "for audit and
  tuning."

**Database:**

```text
fraud_db: fraud_checks
```

Every migration in every service is verified with a real
`upgrade → downgrade → upgrade` cycle before being committed. This caught
two real bugs: PostgreSQL native enum types aren't dropped by
`drop_table()` (identity-service's first migration originally left
`user_status` behind), and reusing a native enum type across two tables'
columns requires the dialect-specific `postgresql.ENUM(create_type=False)`
— the generic `sqlalchemy.Enum(create_type=False)` silently ignores the
flag and fails with "type already exists." Both are now covered by
regression tests in `tests/integration/test_migrations.py` in each
service.

### Distributed tracing (all services)

Every service calls `fincore_common.configure_tracing()` at startup
(spec Section 24), which instruments FastAPI and httpx and exports spans
via OTLP to Jaeger. The part worth calling out specifically:
`fincore_common.kafka`'s `EventProducer`/`EventConsumer` inject and
extract W3C trace context into Kafka message headers around
publish/consume, so a trace continues across the async Kafka boundary
as the *same* trace instead of breaking into two disconnected ones —
verified both with a real Kafka broker + an in-memory span exporter in
`fincore-common`'s own tests, and by querying Jaeger's API after a real
transfer through the live stack: `payment-service`'s `transfers publish`
span and `notification-service`'s `transfers process` span share one
trace id. `/ready` also checks Kafka connectivity now, not just the
database, for any service that talks to Kafka.

---

## Run it

### Docker Compose (the whole stack)

```bash
cp services/identity-service/.env.example services/identity-service/.env
# then edit JWT_PRIVATE_KEY in that .env — generate one with:
openssl genpkey -algorithm ed25519

cp services/ledger-service/.env.example services/ledger-service/.env
# then edit INTERNAL_SERVICE_TOKEN in that .env to any random local value

cp services/fraud-service/.env.example services/fraud-service/.env
# then edit INTERNAL_SERVICE_TOKEN in that .env to the *same* value as
# ledger-service's/payment-service's — payment-service sends one shared
# internal token to every internal API it calls

cp services/payment-service/.env.example services/payment-service/.env
# then edit INTERNAL_SERVICE_TOKEN in that .env to the *same* value as
# ledger-service's — cross-service internal auth is one shared secret

cp services/notification-service/.env.example services/notification-service/.env
# then edit INTERNAL_SERVICE_TOKEN in that .env to any random local value
# (this one is its own secret — nothing else calls into it)

docker compose up --build
```

| Via gateway | Direct |
|---|---|
| `http://localhost:8180` | `http://localhost:8091` (identity-service), `http://localhost:8092` (ledger-service), `http://localhost:8093` (payment-service), `http://localhost:8094` (notification-service), `http://localhost:8095` (fraud-service) |

Swagger UI (FastAPI's auto-generated API docs):
`http://localhost:8091/docs`, `http://localhost:8092/docs`,
`http://localhost:8093/docs`, `http://localhost:8094/docs`, and
`http://localhost:8095/docs`.

Jaeger UI (distributed traces): `http://localhost:16686`. Kafka's own
external port (for `kcat`/`kafka-console-consumer` from the host, not
needed by the services themselves — they talk to `kafka:9092` inside the
compose network) is `http://localhost:9094`.

`/internal/*` routes (postings, holds, reconciliation) are deliberately
**not** reachable through the gateway (`8180`) — only directly against
`ledger-service` (`8092`, or by its service name from inside the Docker
network), matching Section 19. Verified:
`curl -X POST localhost:8180/internal/v1/postings` returns `404`; the
same path against `localhost:8092` reaches the route (and then rejects a
missing/wrong `X-Internal-Token`).

`payment-service` has no wallet balance to fund a transfer with out of
the box — there's no public deposit endpoint yet (Phase 5). To try a
transfer end to end locally, credit a wallet directly via
`ledger-service`'s internal API first:

```bash
curl -X POST localhost:8092/internal/v1/postings \
  -H "X-Internal-Token: <your INTERNAL_SERVICE_TOKEN>" \
  -H 'Content-Type: application/json' \
  -d '{"source_service":"manual","source_id":"seed-1","type":"DEPOSIT","currency":"UZS",
       "entries":[{"account_id":"<EXTERNAL_FUNDING account id for UZS>","direction":"DEBIT","amount_minor":10000000},
                  {"account_id":"<your wallet id>","direction":"CREDIT","amount_minor":10000000}]}'
```

> `docker-compose.yml`'s host ports (`8180`/`8091`-`8095`/`5440`/`9094`
> instead of the more usual `8080`/`8001`.../`5432`/`9092`) were picked
> to avoid clashing with other local projects on this dev machine — the
> internal container ports are unaffected. Change the left side of each
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

`payment-service` needs `identity-service` (JWKS), `ledger-service`
(postings, wallet ownership checks), and a running Kafka broker (the
outbox relay):

```bash
cd services/payment-service
python3.12 -m venv .venv
.venv/bin/pip install -e "../../libs/fincore-common[kafka]"
.venv/bin/pip install -e ".[dev]"

cp .env.example .env   # fill in DATABASE_URL, IDENTITY_SERVICE_JWKS_URL,
                        # INTERNAL_SERVICE_TOKEN (must match ledger-service's),
                        # LEDGER_SERVICE_BASE_URL, FRAUD_SERVICE_BASE_URL

docker run --rm -d --name fincore-payment-dev \
  -e POSTGRES_USER=payment -e POSTGRES_PASSWORD=payment -e POSTGRES_DB=payment_db \
  -p 5434:5432 postgres:16-alpine

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8002
```

Pointing `FRAUD_SERVICE_BASE_URL` at a host nothing answers on (instead
of a running `fraud-service`) is still a legitimate way to exercise the
fail-open/fail-closed policy end to end without standing up a second
service.

`fraud-service` has no dependency on any other service — just its own
Postgres:

```bash
cd services/fraud-service
python3.12 -m venv .venv
.venv/bin/pip install -e ../../libs/fincore-common
.venv/bin/pip install -e ".[dev]"

cp .env.example .env   # fill in DATABASE_URL, INTERNAL_SERVICE_TOKEN
                        # (must match payment-service's)

docker run --rm -d --name fincore-fraud-dev \
  -e POSTGRES_USER=fraud -e POSTGRES_PASSWORD=fraud -e POSTGRES_DB=fraud_db \
  -p 5436:5432 postgres:16-alpine

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8004
```

`notification-service` needs a running Kafka broker and its own
Postgres — it doesn't call any other service directly:

```bash
cd services/notification-service
python3.12 -m venv .venv
.venv/bin/pip install -e "../../libs/fincore-common[kafka]"
.venv/bin/pip install -e ".[dev]"

cp .env.example .env   # fill in DATABASE_URL, INTERNAL_SERVICE_TOKEN

docker run --rm -d --name fincore-notification-dev \
  -e POSTGRES_USER=notification -e POSTGRES_PASSWORD=notification -e POSTGRES_DB=notification_db \
  -p 5435:5432 postgres:16-alpine

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8003
```

A local Kafka broker for either of the two above (matching
`docker-compose.yml`'s single-node KRaft setup, no Zookeeper):

```bash
docker run --rm -d --name fincore-kafka-dev -p 9094:9094 \
  -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,EXTERNAL://0.0.0.0:9094 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092,EXTERNAL://localhost:9094 \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,EXTERNAL:PLAINTEXT \
  -e KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true \
  -e CLUSTER_ID=MkU3OEVBNTcwNTJENDM2Qk confluentinc/cp-kafka:7.6.0
# then set KAFKA_BOOTSTRAP_SERVERS=localhost:9094 in both services' .env
```

Tracing works without any extra setup — `configure_tracing()` degrades
to dropped spans if `OTEL_EXPORTER_OTLP_ENDPOINT` isn't reachable. Run
Jaeger locally to actually see them:

```bash
docker run --rm -d --name fincore-jaeger-dev -p 16686:16686 -p 4318:4318 \
  -e COLLECTOR_OTLP_ENABLED=true jaegertracing/all-in-one:1.60
```

---

## Testing

```bash
cd libs/fincore-common && .venv/bin/pytest -v           # 40 tests
cd services/identity-service && .venv/bin/pytest -v     # 52 tests
cd services/ledger-service && .venv/bin/pytest -v       # 53 tests
cd services/payment-service && .venv/bin/pytest -v      # 64 tests
cd services/notification-service && .venv/bin/pytest -v # 25 tests
cd services/fraud-service && .venv/bin/pytest -v        # 26 tests
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
* `test_concurrent_requests_with_the_same_new_key_let_only_one_proceed`
  — races two requests carrying the same `Idempotency-Key`, asserting
  the `UNIQUE(user_id, key)` constraint, not a pre-check, decides which
  one runs the business logic (payment-service)
* `test_two_concurrent_resolutions_of_the_same_transfer_write_exactly_one_outbox_event`
  — the saga's own call and the recovery worker racing to resolve the
  same transfer; only one may write the outbox event (payment-service)
* `test_two_concurrent_first_time_checks_for_the_same_operation_produce_one_row`
  — races two risk checks for the same operation id; the
  `UNIQUE(operation_id, operation_type)` constraint decides (fraud-service)

Several more tests run against a real single-node Kafka broker via
`testcontainers` (never a fake producer/consumer) — the same "no fakes
for infra" rule as PostgreSQL. Two are worth calling out specifically:
`test_a_failed_handler_leaves_the_message_uncommitted_for_redelivery`
proves a raised exception really does leave a message's offset
uncommitted for redelivery rather than just asserting the code path was
reached, and `test_trace_context_propagates_from_producer_to_consumer`
proves a trace started before publishing continues as the parent of the
consumer's own span, using a real broker plus an in-memory span exporter
(fincore-common).

```bash
cd services/identity-service && .venv/bin/ruff check . && .venv/bin/mypy app
cd services/ledger-service && .venv/bin/ruff check . && .venv/bin/mypy app
cd services/payment-service && .venv/bin/ruff check . && .venv/bin/mypy app
cd services/notification-service && .venv/bin/ruff check . && .venv/bin/mypy app
cd services/fraud-service && .venv/bin/ruff check . && .venv/bin/mypy app
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
before `payment-service`'s implementation and matched by it, Phase 3).

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
| A transfer's fraud check comes back BLOCK | `FAILED` without ever calling `ledger-service` — verified by asserting the fake ledger received zero posting calls, not just by the resulting status |
| A transfer's fraud check comes back REVIEW | Stays `PENDING` |
| `fraud-service` is unreachable and the amount is at or under the fail-open limit | Treated as `ALLOW` (flagged), so a monitoring outage doesn't halt all transfers |
| `fraud-service` is unreachable and the amount is over the fail-open limit | Treated as `REVIEW` — the riskier the amount, the less a monitoring outage is allowed to auto-approve it |
| The same operation is risk-checked twice (retry after a timeout) | The second call returns the *stored* result instead of re-scoring — and doesn't double-count itself in the frequency-based rules' own history lookups |
| Two concurrent first-time risk checks arrive for the same operation | Exactly one is scored — the `UNIQUE(operation_id, operation_type)` constraint decides, not a pre-check |
| `ledger-service` returns a 5xx or is unreachable while posting a transfer | The transfer stays `PROCESSING`, **never** `FAILED` — money may or may not have actually moved, and reporting failure when it didn't would be worse than an operation left open |
| A transfer stuck `PROCESSING` past the recovery threshold | The recovery worker retries the same posting call on its own schedule; safe because the posting is idempotent on `(source_service, source_id, type)` |
| The same `Idempotency-Key` is replayed with an identical body | The original response is returned verbatim; the saga never runs twice |
| The same `Idempotency-Key` is reused with a *different* body | `422 Idempotency Key Conflict` |
| Two requests race with the same brand-new `Idempotency-Key` | Exactly one runs the business logic — the `UNIQUE(user_id, key)` constraint decides, not a pre-check |
| A transfer is requested from a wallet the caller doesn't own, or between the same wallet twice | `404 Wallet Not Found` / `422 Same Wallet Transfer` — checked before any state is created |
| The ledger's own invariants drift from what its entry log actually implies (posting unbalanced, a cached balance out of sync, a duplicate posting, a wallet's available balance negative) | The reconciliation job catches it on its next pass and logs it as an incident — it never silently "fixes" the numbers |
| `payment-service` crashes between committing a transfer's status and the outbox relay publishing its event | The event is still there on restart — it was committed in the *same* transaction as the status change, not a follow-up step that could be lost |
| The recovery worker and the saga's own call both try to resolve the same stuck transfer | Only the one whose `UPDATE ... WHERE status = :expected` actually applies gets to write the outbox event — the other sees it already moved on |
| `notification-service` crashes between dispatching a notification and committing its offset | The event redelivers on restart; `notifications.event_id` is `UNIQUE`, so the redelivery is a no-op, not a second notification |
| A notification handler raises for reasons that will never resolve (malformed event data) | Dead-lettered immediately — no retries wasted on something retrying can't fix |
| A notification handler raises for a reason that might resolve (a provider timeout) | Routed to the retry topic with exponential backoff + jitter, delaying only that topic's partition — every other queued event keeps flowing |
| A transient failure exhausts its retry attempts | Dead-lettered, recorded in a queryable table, and republishable on demand via the internal replay API |
| `payment-service` or `notification-service` starts up with Kafka unreachable | `/ready` returns `503` — it checks Kafka connectivity now, not just the database |
| A collector for distributed tracing isn't running | Spans queue in a background thread and get silently dropped — request handling is never blocked or failed by tracing infrastructure being down |

---

## Roadmap

Full detail in `docs/spec.md` Section 27. Status here is updated as
phases complete — not aspirational.

| Phase | Weeks | Scope | Status |
|---|---|---|---|
| 0 — Design | 0 | Glossary, context map, ADRs, saga diagram | ✅ |
| 1 — Foundation | 1–3 | `fincore-common`, `identity-service`, gateway, Docker Compose, CI | ✅ |
| 2 — Core Ledger | 4–6 | `ledger-service`, postings, holds, row locking | ✅ |
| 3 — Transfers & Distributed Consistency | 7–9 | `payment-service`, sagas, idempotency, recovery worker | ✅ |
| 4 — Async Architecture | 10–11 | Transactional outbox, Kafka, `notification-service`, tracing | ✅ |
| 5 — Advanced Financial Features | 12–14 | `fraud-service`, payment holds/refunds, `webhook-service`, `audit-service` | ⏳ |
| 6 — Production Readiness | 15–16 | Prometheus/Grafana, full CI, e2e, load testing | ⏳ |
| 7 — Frontend | after 6 | React/TypeScript dashboard + admin panel ([ADR-0005](docs/adr/0005-frontend-addition.md)) | ⏳ |

Per the spec's own rule: if time runs short, webhook/dashboard scope
shrinks first — the ledger, idempotency, and consistency work is never
shortened.

# FinCore

A digital wallet and payment platform built as a microservices system, in
the style of a real core-banking backend: database-per-service,
double-entry ledger, sagas for distributed consistency, transactional
outbox, and asymmetric-JWT auth with JWKS.

This is a learning-driven, production-oriented portfolio project — not a
tutorial. Every non-obvious decision is recorded as an [ADR](docs/adr/)
rather than left implicit, and the full design rationale lives in
[`docs/spec.md`](docs/spec.md).

**Status: Phase 1 (Foundation) — `identity-service` v0.1 is complete.**
Ledger, payments, fraud, notifications, webhooks, and audit are designed
(see the ADRs and [`docs/context-map.md`](docs/context-map.md)) but not
yet built. The table in [Roadmap](#roadmap) below tracks this precisely —
nothing here is described as done unless it's tested and running.

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
| `ledger-service` | ledger accounts, postings, entries, balances, holds | Core banking; accepts balanced postings only, knows nothing about *why* — this is what keeps it the most stable service in the system |
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

## What's implemented: `identity-service`

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

### Database

```text
identity_db: users, roles, user_roles, sessions, refresh_tokens
```

`roles` is seeded with `USER` / `SUPPORT` / `ADMIN` by its own migration.
Every migration is verified with a real `upgrade → downgrade → upgrade`
cycle before being committed (this caught a real bug: PostgreSQL native
enum types aren't dropped by `drop_table()`, so the first migration's
`downgrade()` originally left `user_status` behind — fixed, and now
covered by a regression test in
`tests/integration/test_migrations.py`).

---

## Run it

### Docker Compose (the whole stack)

```bash
cp services/identity-service/.env.example services/identity-service/.env
# then edit JWT_PRIVATE_KEY in that .env — generate one with:
openssl genpkey -algorithm ed25519

docker compose up --build
```

| Via gateway | Direct |
|---|---|
| `http://localhost:8180` | `http://localhost:8091` (identity-service) |

Swagger UI (FastAPI's auto-generated API docs): `http://localhost:8091/docs`.

> `docker-compose.yml`'s host ports (`8180`, `8091`, `5440` instead of
> the more usual `8080`/`8001`/`5432`) were picked to avoid clashing with
> other local projects on this dev machine — the internal container ports
> are unaffected. Change the left side of each `"host:container"` mapping
> in `docker-compose.yml` if these also collide with something on your
> machine.

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

---

## Testing

```bash
cd libs/fincore-common && .venv/bin/pytest -v
cd services/identity-service && .venv/bin/pytest -v
```

Integration tests spin up a real PostgreSQL container via `testcontainers`
— concurrency and locking behavior is never trustworthy on SQLite, so it's
never used here (spec Section 23). This includes real concurrency tests,
not just sequential ones: `test_concurrent_registration_with_the_same_email_rejects_one`
and `test_concurrent_redemption_of_the_same_token_lets_only_one_succeed`
both use `asyncio.gather` to race two requests against each other and
assert the database — not application code timing — decides the winner.

```bash
cd services/identity-service
.venv/bin/ruff check .
.venv/bin/mypy app
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

Saga-level failure handling (a ledger call timing out mid-transfer, an
"unknown outcome," recovery workers, reconciliation) is designed in
[ADR-0003](docs/adr/0003-sync-vs-async-communication.md) and the
[transfer saga diagram](docs/diagrams/transfer-saga.md), and will move
into this table once `payment-service` and `ledger-service` exist
(Phases 2–3).

---

## Roadmap

Full detail in `docs/spec.md` Section 27. Status here is updated as
phases complete — not aspirational.

| Phase | Weeks | Scope | Status |
|---|---|---|---|
| 0 — Design | 0 | Glossary, context map, ADRs, saga diagram | ✅ |
| 1 — Foundation | 1–3 | `fincore-common`, `identity-service`, gateway, Docker Compose, CI | ✅ |
| 2 — Core Ledger | 4–6 | `ledger-service`, postings, holds, row locking | ⏳ |
| 3 — Transfers & Distributed Consistency | 7–9 | `payment-service`, sagas, idempotency, recovery worker | ⏳ |
| 4 — Async Architecture | 10–11 | Transactional outbox, Kafka, `notification-service`, tracing | ⏳ |
| 5 — Advanced Financial Features | 12–14 | `fraud-service`, payment holds/refunds, `webhook-service`, `audit-service` | ⏳ |
| 6 — Production Readiness | 15–16 | Prometheus/Grafana, full CI, e2e, load testing | ⏳ |
| 7 — Frontend | after 6 | React/TypeScript dashboard + admin panel ([ADR-0005](docs/adr/0005-frontend-addition.md)) | ⏳ |

Per the spec's own rule: if time runs short, webhook/dashboard scope
shrinks first — the ledger, idempotency, and consistency work is never
shortened.

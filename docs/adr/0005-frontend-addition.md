# ADR-0005: Add a Frontend (React + TypeScript)

## Status

Accepted

## Context

`spec.md` (Sections 1, 4, and "Final Context") describes FinCore as a
purely backend, microservices learning project — the technology stack,
roadmap, and stated learning objectives contain no frontend work. The
"UI" implied by the original spec is Swagger/OpenAPI docs (Section 29)
plus, later, Grafana/Jaeger dashboards (Phase 6).

The project owner has since decided the finished portfolio piece should
include a real, complete user-facing application on top of the backend,
not just API documentation. This is a deliberate scope change, not a
correction of a mistake in the original spec — recorded here rather than
by editing `spec.md`, the same way every other ADR layers a decision on
top of the spec without rewriting it.

## Decision

### Stack

**React + TypeScript + Vite** — a client-rendered SPA.

Server-side rendering (Next.js) is not used: FinCore's frontend is an
authenticated dashboard (wallet balances, transfers, admin tools), not a
content or marketing site, so SSR's main benefits (SEO, fast first paint
for public content) don't apply, and it would add a routing/data-fetching
framework the app doesn't need. Vue was considered and rejected only
because React was the project owner's preference — both would have been
reasonable technically (see Alternatives).

### Scope

A **full user dashboard** plus a **support/admin panel**, matching the
RBAC roles already defined in `spec.md` Section 5 (`USER`, `SUPPORT`,
`ADMIN`):

* **User dashboard** (`USER` role): register/login, wallet list and
  balances, send a transfer, view transaction/payment history, profile
  and session management (view/revoke active sessions — pairs naturally
  with the refresh-token-family model in Section 5).
* **Admin/support panel** (`SUPPORT`, `ADMIN` roles): user lookup and
  status management (`BLOCKED`/`SUSPENDED`), fraud review queue (approve
  or reject transfers parked in `REVIEW`, Section 7.3), transaction
  oversight, webhook endpoint management.

The frontend calls **only** the public API surface through the gateway
(`/api/v1/*`, Section 20) — never `/internal/*` endpoints. It is a client
of FinCore exactly like any third-party integrator would be; this is what
keeps the backend's service boundaries (Section 3) meaningful regardless
of what consumes them.

### Timing

The frontend is built **after the backend's core services are
functionally complete** — starting once identity, ledger, payment, and
fraud are working end-to-end (i.e., around/after Phase 5), rather than in
parallel with backend Phase 1. Reasons:

1. The backend roadmap (Section 27) is already deliberately sequenced so
   that the hardest, most important work (the ledger and the transfer
   saga, Phases 2–3) happens first and is "never shortened." Splitting
   attention with frontend work during those phases risks exactly the
   dilution that rule exists to prevent.
2. Building the dashboard against a stable, real API (not a mocked one)
   avoids throwaway work: request/response shapes, error formats (RFC
   7807), and auth flows should already be settled by the time the UI is
   built against them.
3. The admin panel specifically needs fraud-service's `REVIEW` queue and
   webhook-service's endpoint management to exist first — both are Phase
   5 deliverables.

### Where it lives

A new top-level `frontend/` directory, alongside `services/` and `libs/`,
**not** inside either:

```text
fincore/
├── services/     (backend microservices — unchanged)
├── libs/         (backend shared libraries — unchanged)
├── frontend/     (new: React + TypeScript + Vite SPA)
│   ├── src/
│   ├── package.json
│   └── ...
├── gateway/
└── ...
```

The gateway (Nginx) gains a route for serving/proxying the frontend
alongside its existing `/api/v1/*` routing when the frontend is built —
not before, per Section 25's "do not create unnecessary infrastructure
before the application needs it."

### Auth handling (flagged now, finalized when built)

The SPA authenticates the same way any API client does (Section 5): it
calls `/api/v1/auth/login`, receives a short-lived JWT access token and an
opaque refresh token. The exact browser-side storage strategy (in-memory
access token vs. httpOnly cookie for the refresh token, silent-refresh
timing) is a security-sensitive decision deferred to when the frontend
auth flow is actually implemented — it is called out here so it isn't
forgotten, not decided now.

## Consequences

* The 16-week backend roadmap (Section 27) gains a frontend phase after
  Phase 5/6; exact placement is revisited when the backend reaches that
  point rather than fixed now.
* CI (Section 26) eventually needs a frontend pipeline (lint, type-check,
  build, and later e2e against a running backend) — added when the
  frontend directory is created, not now.
* The project's learning scope (`spec.md` "Final Context") is now broader
  than originally stated: it includes building a production-quality React
  client against the microservices backend, in addition to the backend
  topics already listed.
* `README.md` and Section 29's portfolio checklist will need a frontend
  section (screenshots, run instructions) once it exists.

## Alternatives Considered

* **Next.js** — rejected: its SSR/file-based routing and data-fetching
  conventions solve problems (SEO, public-content performance) FinCore's
  authenticated dashboard doesn't have; adopting it would be exactly the
  kind of unjustified technology addition Section 4 warns against.
* **Vue 3 + TypeScript** — a technically equivalent alternative to React
  for this use case; not chosen, per the project owner's stack
  preference.
* **Building the frontend in parallel with backend Phase 1** — rejected
  for the reasons under "Timing" above: it risks diluting focus on the
  ledger/saga work the spec explicitly calls the most important, least
  shortenable phase.
* **No frontend, Swagger/OpenAPI only** (the original spec's position) —
  superseded by this ADR at the project owner's explicit request.

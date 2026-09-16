# ADR-0001: Money Representation

## Status

Accepted

## Context

FinCore stores and moves real (simulated) money. The original v1 draft of
the spec left the money format unspecified, which is a defect on its own:
without an explicit decision, it is easy to end up with `float` amounts
somewhere in the stack (a Python `float` field, a JSON number parsed as
`float`, a `FLOAT`/`DOUBLE` database column). Floats use binary
floating-point representation and cannot represent most decimal fractions
exactly (e.g. `0.1 + 0.2 != 0.3`), which is unacceptable for financial
amounts — rounding errors compound across millions of postings and are a
direct path to ledger imbalance.

We need one representation that is:

* exact for every currency's minor unit,
* safe to add, subtract, and compare without rounding surprises,
* usable consistently across every service's database, application code,
  and public API — a mismatch anywhere reopens the float problem at the
  boundary.

## Decision

1. **Storage:** every amount is stored as an integer number of the
   currency's minor units, in a `BIGINT` column named `amount_minor` (or a
   suffix ending in `_minor`, e.g. `balance_minor`, `held_minor`).
   `BIGINT` gives headroom far beyond any realistic balance even for
   currencies with 2 decimal places.
2. **Currency:** every amount is stored alongside an ISO 4217 currency code
   (e.g. `UZS`, `USD`). The minor-unit exponent for each supported currency
   (2 for both UZS and USD in v1) is defined once in shared configuration
   (`fincore-common`), not hardcoded per service.
3. **Application code:** Python code never represents money as `float`.
   Where arithmetic on major units is needed (rare — mostly at the API
   boundary), `decimal.Decimal` is used, constructed from strings, never
   from `float`.
4. **Public API:** amounts cross the HTTP boundary as **decimal strings**,
   e.g. `"100000.00"`, never as JSON numbers. JSON numbers are ambiguous
   (many client libraries decode them as `float`), so encoding as a string
   forces the client and server to both go through explicit, exact
   parsing.
5. **Boundary validation:** an incoming decimal string is validated against
   the currency's minor-unit exponent (e.g. `"100.5"` is rejected for UZS
   if UZS has 0 fractional minor-unit ambiguity — precision must match
   exactly) and converted to `amount_minor` via `Decimal`, never via
   `float(...)`. Invalid precision (too many decimal places, wrong
   separator, non-numeric input) is rejected with a `422`, never silently
   rounded.
6. **Never**: no `float`/`DOUBLE PRECISION` column, no `float` field in a
   Pydantic model, no `float()` cast anywhere near an amount, in any
   service, at any layer.

## Consequences

* Every service that touches money needs a small, shared helper (in
  `fincore-common`) for decimal-string ⇄ minor-units conversion, so the
  rule is enforced once instead of reimplemented per service.
* Multiplying/dividing minor-unit integers (e.g. fee percentages) requires
  explicit rounding rules (defined when fees are implemented in Phase 5) —
  this is a deliberate, visible decision point rather than an implicit
  float truncation.
* Database migrations must use `BIGINT`, not `NUMERIC`/`FLOAT`, for money
  columns; this is checked in code review, not enforced automatically in
  v1.
* API consumers must send/parse amounts as strings, which is slightly less
  convenient than raw JSON numbers but removes an entire class of
  precision bugs.

## Alternatives Considered

* **`NUMERIC`/`DECIMAL` database column in major units** — avoids float
  issues at the DB layer, but reintroduces ambiguity about how many
  decimal places are valid per currency, and Python's `Decimal` still has
  to be handled carefully at every arithmetic step; integer minor units
  make "is this exact?" a non-question by construction.
* **`float` with rounding on every operation** — rejected outright; no
  amount of careful rounding makes float exact, and the failure mode
  (silent balance drift) is the worst possible one for a ledger.
* **JSON numbers for amounts in the API** — rejected because many JSON
  parsers/clients decode numeric literals as `float`/`double` by default,
  silently reintroducing the exact problem this ADR avoids.

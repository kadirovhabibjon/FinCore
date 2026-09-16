# ADR-0002: Ledger Model — Accounts, Sign Convention, Holds

## Status

Accepted

## Context

The original v1 spec described transfers as balance mutations
(`wallet.balance -= amount`) with no counterpart account for deposits or
payments. That model breaks as soon as money needs to enter or leave the
system from outside (deposits, withdrawals, merchant settlement, fees): a
single mutable balance field has no way to express *where the money came
from or went to*, cannot be audited, and cannot express a "hold" (reserved
but not yet moved) separately from a real movement.

Double-entry bookkeeping fixes this: every movement is recorded as a
**posting** — a balanced set of **entries**, each hitting one account with
a `DEBIT` or `CREDIT` direction, such that `sum(DEBIT) == sum(CREDIT)` for
every posting. This makes every movement self-documenting (it always has
two sides) and makes the sum of all entries in the system always net to
zero, which is a strong, continuously-checkable invariant.

Adopting double-entry requires two things the original spec did not
specify: (1) a fixed **sign convention** — what does a debit or credit mean
for each kind of account — and (2) a model for **holds**, since merchant
payments need a reserve-then-capture flow rather than an instant transfer.

## Decision

### Account kinds

```text
USER_WALLET           customer money held by FinCore (liability)
EXTERNAL_FUNDING       counterpart for deposits from outside
EXTERNAL_PAYOUT        counterpart for withdrawals to outside
MERCHANT_SETTLEMENT    money owed to merchants (liability)
FEES                   fee revenue
SUSPENSE               temporary holding for unresolved items
```

System accounts (everything except `USER_WALLET`) exist once per currency
and have no `owner_user_id`.

### Sign convention

Every account kind has a fixed **normal balance side** — the direction on
which its balance *increases*:

| Account kind | Accounting nature | Normal side | A debit... | A credit... |
|---|---|---|---|---|
| `USER_WALLET` | Liability (we owe the customer) | CREDIT | decreases balance | increases balance |
| `MERCHANT_SETTLEMENT` | Liability (we owe the merchant) | CREDIT | decreases balance | increases balance |
| `FEES` | Revenue | CREDIT | decreases balance | increases balance |
| `EXTERNAL_FUNDING` | Clearing (tracks cumulative inbound funding) | DEBIT | increases balance | decreases balance |
| `EXTERNAL_PAYOUT` | Clearing (tracks cumulative outbound payouts) | CREDIT | decreases balance | increases balance |
| `SUSPENSE` | Clearing, no normal side | — | must net to zero across resolved postings | must net to zero across resolved postings |

`balance_minor` for an account is always computed as:
`sum(entries on the normal side) − sum(entries on the opposite side)`.

This is derived directly from the two worked examples already in the spec,
and both check out under this table:

```text
Transfer 100,000 UZS, A → B
  DEBIT   A wallet    100,000   (CREDIT-normal → debit decreases A's balance: correct, A paid out)
  CREDIT  B wallet    100,000   (CREDIT-normal → credit increases B's balance: correct, B received)

Deposit 50,000 UZS
  DEBIT   EXTERNAL_FUNDING  50,000   (DEBIT-normal → debit increases it: cumulative funding grows)
  CREDIT  User wallet       50,000   (CREDIT-normal → credit increases it: correct, user received)
```

By symmetry, a withdrawal is:

```text
Withdrawal 30,000 UZS
  DEBIT   User wallet        30,000   (decreases user's balance: correct, money leaves)
  CREDIT  EXTERNAL_PAYOUT    30,000   (CREDIT-normal → credit increases it: cumulative payouts grow)
```

`EXTERNAL_FUNDING` and `EXTERNAL_PAYOUT` are deliberately given *opposite*
normal sides even though both are "external counterpart" accounts: each is
defined so that it grows via the same direction that represents money
*entering FinCore from outside* (debit, for funding) or *leaving FinCore to
outside* (credit, for payout) respectively — matching how a wallet
(liability) moves for the same event. This keeps every posting balanced
while still letting `EXTERNAL_FUNDING`'s and `EXTERNAL_PAYOUT`'s balances
be read directly as running totals.

`SUSPENSE` has no normal side: it exists purely to receive one leg of a
posting when an automated process cannot yet determine the correct
counterpart account, and reconciliation treats any non-zero, aged
`SUSPENSE` balance as an incident to investigate — never as a valid steady
state.

### Structure

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
- source_id              (e.g. transfer id)
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

Postings and entries are **append-only**: never `UPDATE`d or `DELETE`d.
Corrections are made with a **reversal posting** (a new posting with the
same amounts and accounts but swapped directions), never by editing
history.

A posting is rejected unless (a) `sum(DEBIT) == sum(CREDIT)`, and (b) every
account in it shares the posting's currency. These are enforced in code
and backed by DB constraints (`CHECK`, `NOT NULL`) as the last line of
defense.

### Locking and balance checks

Accounts touched by a posting are locked with `SELECT ... FOR UPDATE` in
**ascending `account_id` order**, so that two postings touching the same
two accounts in opposite "directions" (e.g. A→B and B→A concurrently)
always acquire locks in the same order and cannot deadlock each other. The
available-balance check (`balance_minor - held_minor >= amount` for a
`USER_WALLET`) happens **after** the lock is acquired, inside the same
transaction as the entry inserts and balance update — never before,
avoiding the TOCTOU race the original spec was vulnerable to.

A posting, its entries, the resulting balance update, and its outbox event
are written in **one local database transaction**.

### Holds

A hold reserves funds on a `USER_WALLET` without moving money, supporting
merchant payments' reserve → capture (or reserve → release) flow.

```text
Hold
- id
- account_id
- amount_minor
- currency
- status (ACTIVE | CAPTURED | RELEASED | EXPIRED)
- source_service, source_id   ← idempotency, same pattern as Posting
- created_at
- expires_at
- resolved_at
```

* **Create hold:** lock the account, verify
  `balance_minor - held_minor >= amount`, increment `held_minor`, insert
  `Hold(ACTIVE)`. No posting is created — no money has moved yet.
* **Capture:** lock the account, decrement `held_minor` by the captured
  amount, create a real posting (e.g. `DEBIT` user wallet / `CREDIT`
  `MERCHANT_SETTLEMENT`), mark the hold `CAPTURED`. A capture for less than
  the held amount releases the remainder.
* **Release:** lock the account, decrement `held_minor` by the released
  amount, mark the hold `RELEASED`. No posting — no money ever moved.
* **Expire:** an automated job releases holds past `expires_at` the same
  way as an explicit release, so abandoned payment attempts don't
  permanently lock funds.

Holds are idempotent the same way postings are: `(source_service,
source_id)` identifies a hold uniquely, so retried hold/capture/release
calls are safe.

### Reconciliation invariants

A periodic job verifies, for every account and every posting:

```text
per posting:  sum(debits) == sum(credits)
per account:  account_balances.balance_minor == sum of its entries (signed per the table above)
per wallet:   balance_minor - held_minor >= 0
per transfer: at most one posting exists for its source_id
```

Any violation is an incident, not a value to silently correct.

## Consequences

* Every money movement, including ones that will only be implemented in
  later phases (fees, refunds), must be expressible as a balanced posting
  against this fixed set of account kinds — no ad hoc balance mutation is
  ever introduced.
* `SUSPENSE` and the reconciliation job give the system a documented way to
  fail safely (park the problem, alert, investigate) instead of either
  blocking the request pipeline or silently guessing.
* The sign convention must be implemented once, correctly, in
  `ledger-service`'s domain layer (never re-derived ad hoc per code path),
  since every other service treats postings as opaque and trusts
  `ledger-service` to be correct.

## Alternatives Considered

* **Single mutable `wallet.balance` column** (original v1 draft) — rejected:
  no counterpart for deposits/withdrawals, no audit trail, no way to
  express holds, and directly vulnerable to the TOCTOU race described in
  the spec's revision notes.
* **One normal side for all account kinds** (e.g. treat everything as
  asset-like) — rejected: it would make wallet balances increase on debit,
  which is unintuitive to every future reader familiar with either
  accounting or the spec's own worked examples, and would require flipping
  the sign at every read site instead of once in the account-kind
  definition.
* **No `held_minor` (holds modelled as a real posting into `SUSPENSE`)** —
  rejected: it would create a posting for money that never actually moved,
  muddying "postings are real money movements" and complicating
  reconciliation (`SUSPENSE` would never be empty in normal operation).

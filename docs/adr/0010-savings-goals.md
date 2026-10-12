# ADR-0010: Savings goals as a pooled ledger account

## Status

Accepted

## Context

Customers wanted to set money aside for something - "a new phone,
5,000,000 UZS" - where it can't be spent by mistake, and see how far
along they are. The money has to really leave the wallet: a goal that
is only a number next to an unchanged balance protects nothing.

So the ledger needs somewhere for that money to be. A customer has one
wallet per currency (ADR-0002, enforced by a unique index), and may have
several goals in it.

## Decision

**One pooled `SAVINGS` system account per currency holds everything
customers have set aside; which goal holds how much is payment-service's
to know.** This is the shape `MERCHANT_SETTLEMENT` already has: the
ledger moves money between a wallet and a pooled account and knows
nothing of merchants, or of goals.

    set aside:  DEBIT  customer's wallet   CREDIT SAVINGS (currency)
    take back:  DEBIT  SAVINGS (currency)  CREDIT customer's wallet

Both are ordinary balanced single-currency postings of a new type,
`SAVINGS`. Every existing invariant holds unchanged, and one is added:
like a wallet, **the pool may never go negative** - checked by the
ledger on every posting and by the reconciliation job - so no bug
upstream can hand out more than was set aside.

**payment-service keeps each goal's own figure, `saved_minor`, and it
changes only in the transaction that settles a movement:**

* A deposit is posted first; the goal grows when the posting is
  confirmed.
* A withdrawal shrinks the goal first, in the transaction that records
  it (`UPDATE ... WHERE saved_minor >= :amount`: two withdrawals at once
  cannot both take the last of it), then posts; if the ledger refuses,
  the amount goes back.

A goal therefore never shows money that is not in the pool, and never
offers money already on its way out. The goals of a currency add up to
its pool, less whatever is in flight.

**An unanswered posting leaves the movement `PENDING`, never `FAILED`**
(the same rule as transfers, ADR-0003): the recovery worker asks again,
the posting is idempotent on the movement's id, and settling is an
atomic compare-and-set on the status - so asking twice settles once.

**Closing a goal** needs it empty with nothing in flight, and takes the
goal's row lock, as recording a deposit does: a deposit can't be closed
over. A closed goal is kept, with its movements - they are records of
money that moved.

## Consequences

* Money in a goal is out of the wallet's available balance: it can't be
  sent, paid, held or exchanged until it is taken back. That is the
  feature.
* Movements are not transfers or payments: they don't appear in History
  or in the spending statistics (the money is still the customer's),
  don't count towards the daily limit, and send no notification. They
  are listed on the goal. A blocked wallet can't pay into a goal - the
  ledger refuses the debit - but can receive from one.
* "Which goal holds how much" lives in one service and "how much is set
  aside in all" in another. Their agreement is an invariant across two
  databases, held by the ordering above rather than by a transaction.
  Nothing checks it continuously yet; a reconciliation of
  `sum(saved_minor)` + in-flight withdrawals against the pool's balance
  is the natural next job, as ADR-0002's is within the ledger.
* No interest, no lock-in, no schedule: a goal is a place, not a
  product. Scheduled deposits would be the scheduled-payments worker
  with one more kind.

## Alternatives Considered

* **A ledger account per goal.** The ledger would know every goal's
  balance, and the cross-service invariant would disappear. But an
  account with an owner is a wallet to every rule in the ledger - one
  per currency, a card number, the owner's settings - and a goal is none
  of those; each rule would need "unless it is a goal". The pooled
  account changes one mapping and one check.
* **A hold on the wallet.** Reserves money without moving it, and
  already exists. But holds expire, are released by captures, and are
  counted as "on hold" on the wallet: a goal would be a payment that
  never completes.
* **A number only, no money moved.** Simple, and not savings.

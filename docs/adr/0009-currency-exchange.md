# ADR-0009: Currency exchange between a customer's own wallets

## Status

Accepted

## Context

A customer could hold UZS and USD wallets but had no way to turn one
into the other. The ledger (ADR-0002) only has single-currency postings
that must balance, which is exactly right for everything else and means
"debit UZS, credit USD" cannot be one posting.

## Decision

**An exchange is two ordinary postings, each against FinCore's own
position in that currency.** A new system account kind, `EXCHANGE`, one
per currency, is the counterparty:

    sell:  DEBIT  customer's UZS wallet   CREDIT EXCHANGE (UZS)
    buy:   DEBIT  EXCHANGE (USD)          CREDIT customer's USD wallet

Each posting balances in its own currency, so every existing invariant
and the reconciliation job hold unchanged. The `EXCHANGE` balances are
FinCore's net intake of each currency through exchanges; they are a
position, not a wallet, and may be negative.

**The two postings are a saga in payment-service**, ordered so the
customer never holds both sums: the source currency is taken first, the
destination currency given second.

    PENDING --sell ok--> DEBITED --buy ok--> COMPLETED
       | sell refused       | buy refused
       v                    v
     FAILED <--reversal-- REVERSING

* Each posting has an idempotent `source_id` (`<exchange id>:sell`,
  `:buy`, `:reverse`) and each status change is an atomic compare-and-
  set, so any step can be repeated safely by the request or by the
  recovery worker, which continues every exchange left between steps.
  The state that matters most is `DEBITED`: the customer's money is
  gone and what they bought has not arrived. It is retried until it
  completes or, if the destination wallet can't be credited, reversed.
* The two `EXCHANGE` account ids are looked up before anything is
  created and stored on the exchange, so no later step depends on a
  lookup.

**Rates and rounding** (ADR-0001 still applies): rates come from the
same public provider as the reference widget, fetched by payment-service
and cached for an hour, as `Decimal`s built from the provider's digits.
The amount bought is computed in integer minor units and rounded *down*,
so a round trip can never create money. If a refresh fails the last
rates are used for up to 36 hours; beyond that exchange answers 503
rather than trade on stale prices. No fee and no spread: this is a
demonstration, and a spread would be one multiplication in one place.

**The customer gets exactly what they agreed to, or nothing.** A quote
endpoint shows what an amount buys; the exchange request carries that
amount back (`expected_destination_amount_minor`) and is refused with
`409 Rate Changed` if the current rate would give anything else. No
quote is stored and nothing is "locked": with a provider that updates
daily, re-checking at execution is simpler than expiring reservations.

Exchanges skip the fraud check: the money never leaves the customer.
They are audited (`exchange.completed` / `exchange.failed`), appear in
the customer's history with both amounts, and notify through the bell.

## Consequences

* FinCore carries exchange-rate risk on its `EXCHANGE` positions. Real
  money would need a spread, position limits and hedging; none exist.
* An exchange can be visible to the customer as "being completed" for
  up to a recovery interval if ledger-service stops answering mid-way.
* If a reversal is itself refused (the source wallet was frozen in the
  meantime), the exchange stays `REVERSING`, is retried, and is logged
  as an error: FinCore owes the customer that amount until it succeeds.
* Only currencies wallets can hold (UZS, USD) can be exchanged, and
  only between one customer's own wallets.

## Alternatives Considered

* **Multi-currency postings in the ledger.** One atomic posting, but it
  breaks "every posting balances in one currency", the invariant the
  whole ledger and its reconciliation are built on.
* **Credit first, debit second.** A failure between the steps would
  leave the customer holding both sums; taking first fails safe for
  FinCore and is recoverable for the customer.
* **Stored quotes with an expiry.** More state and a cleanup job to
  protect against a rate that changes once a day.

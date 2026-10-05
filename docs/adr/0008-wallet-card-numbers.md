# ADR-0008: Wallet card numbers and recipient lookup

## Status

Accepted

## Context

To send money a customer had to paste the recipient's wallet id, a
36-character UUID. Nobody can read one out over the phone or check it by
eye, and the form gave no sign of who the money would reach until it had
already moved. People expect what every payment app here does: type a
card number, see a name, then send.

FinCore has no card processing and is connected to no card network, so
these cannot be real payment cards.

## Decision

**Every wallet gets a 16-digit card number**, stored on the wallet's
ledger account and unique across FinCore.

* Format: prefix `9955`, eleven random digits, a Luhn check digit. The
  leading 9 is the range ISO/IEC 7812 leaves to national assignment, so
  a FinCore number can never be a valid Visa, Mastercard, Uzcard or Humo
  number. The check digit catches a wrong or swapped digit in the
  browser and again on the server, before any lookup.
* Assigned at wallet creation by ledger-service, which owns wallets. A
  collision with an existing number (the unique index decides, not a
  read beforehand) draws another. Wallets that existed before were
  numbered by the migration.
* Permanent and not secret: it only lets someone send money *to* the
  wallet. It identifies a wallet, not a person, so a customer's UZS and
  USD wallets have different numbers and the currency is known before
  sending.
* The wallet UUID stays the identifier everywhere else. A transfer is
  still created with `destination_wallet_id`; the card number is only
  how the sender finds that id.

**The recipient lookup lives in payment-service**
(`GET /api/v1/transfers/recipient`). It needs two facts owned by two
other services: whose wallet a number is (ledger) and what that person
is called (identity). payment-service already orchestrates transfers and
already holds the internal token, so it asks both over their internal
APIs. ledger-service still knows nothing about names, identity-service
nothing about wallets, and the owner's user id never reaches the
browser.

**What a lookup reveals is kept small**, since it turns a number into a
name for anyone signed in:

* first name and last initial only (`Aziza K.`), never the full name,
  email, phone or user id;
* "no such card", "wallet frozen or closed" and "owner's account not
  active" are one identical `404`, so a card number can't be used to
  probe an account's state;
* a service that can't answer is a `503`, never mistaken for "no
  recipient";
* signed-in customers only, and the gateway limits each client to 30
  lookups a minute. With 10^11 possible numbers and a check digit,
  guessing live numbers at that rate is not a practical way to collect
  names.

identity-service's new internal API fails closed: with no
`INTERNAL_SERVICE_TOKEN` configured it rejects every request, rather
than refusing to start (signing in doesn't depend on it).

## Consequences

* Sending money takes one more request, and the Send button stays
  disabled until a recipient is confirmed. If identity-service is down,
  transfers by card number can't be started from the web app, though the
  transfer API itself still works with a wallet id.
* The name shown is a convenience, not a guarantee: two customers can
  share a first name and initial. It is checked once more by the sender,
  not by the system.
* A card number can't be changed or reissued yet. If a customer needs a
  new one (harassment by small transfers, say), that is a new feature.
* These numbers work only inside FinCore. The UI and the assistant's
  knowledge base say so, because "card number" invites the assumption
  that a bank card would work.

## Alternatives Considered

* **Send to a phone number.** Familiar, but a phone number identifies a
  person, not a wallet: the sender couldn't choose or even see the
  currency, and it would let anyone test whether a phone number has a
  FinCore account.
* **Keep the UUID and add a name preview.** Fixes "who am I paying" but
  not "I can't type this".
* **Let the browser call ledger and identity itself.** Would expose user
  ids to the browser and need a public "user by id" endpoint.
* **Real card numbers through a processing partner.** Out of scope: it
  needs a licence, PCI DSS and a partner contract, not code.

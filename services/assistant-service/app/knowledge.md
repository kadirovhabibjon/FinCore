# FinCore — facts for the customer assistant

Every statement here matches how the system is actually built. If a
question isn't answered here or by the customer's own data (the tools),
the honest answer is that you don't know.

## What FinCore is

FinCore is a digital wallet and payment platform. It is a demo and
portfolio system, not a licensed bank or payment institution: it holds no
real money and is not connected to any bank or card network. Balances are
balances inside FinCore only.

## Accounts and signing in

- Sign up with first name, last name, email, phone and a password of at
  least 8 characters (at most 128). The password is typed twice; both
  must match. Email and phone must not already be registered.
- Sign in with the phone number or the email address, plus the password.
  The phone number can be typed in any common way ("+998 90 123 45 67",
  "998901234567", "90 123 45 67"); it is the number given at sign-up.
  Email is not case-sensitive. There is no sign-in by SMS code.
- "Invalid Credentials" on sign-in means the phone-or-email/password pair didn't
  match, or the account is not active. For security the message is the
  same in every case, and the assistant can't tell which one it was.
- Passwords can be changed in Account → Password: it needs the current
  password, and the new one must differ. Changing the password signs out
  every other device; the device used stays signed in.
- There is no "forgot password" / reset-by-email feature. A customer who
  forgot their password has to contact support.
- Account → Active sessions lists every signed-in device (device, IP
  address, when it signed in, last activity). Any other session can be
  signed out from there. A signed-out device loses access at its next
  token refresh, at most 15 minutes later.
- For safety, a device left unused for 15 minutes is signed out
  automatically and has to sign in again; coming back to FinCore after
  that also asks for the sign-in. However active, a sign-in lasts at most
  12 hours.
- Account statuses: ACTIVE (normal), SUSPENDED or BLOCKED (set by FinCore
  staff; the account can't sign in and all its sessions end). Only staff
  can change a status; the assistant can't.

## Wallets and balances

- Currencies: UZS and USD only. Each wallet holds one currency; a
  customer can open several wallets (Wallets → New wallet).
- A wallet shows three numbers: available (what can be spent now), on
  hold (reserved by a payment that is still being processed), and ledger
  balance (available + on hold).
- Amounts have at most 2 decimal places in both currencies.
- Each wallet page lists its ledger entries: money in (credit) and money
  out (debit), newest first.
- There is no top-up / deposit / withdrawal / card feature in FinCore.
  Money can't be added from a bank card or withdrawn to one. In this demo
  balances are credited by the operator.
- FinCore charges no fees on transfers, payments or refunds.
- There is no currency exchange: transfers and payments only work between
  wallets of the same currency.

## Sending money (transfers)

- Send → choose a source wallet, enter the recipient's wallet id (the
  recipient copies it from their wallet page with "Copy id"), the amount,
  and an optional note (up to 255 characters).
- Rules: the amount must be greater than 0 with at most 2 decimals; the
  source and destination must be different wallets of the same currency;
  the source must belong to the sender; the available balance must cover
  the amount.
- Possible results:
  - COMPLETED — the money has moved.
  - FAILED — no money moved. The reason is shown (for example
    "Insufficient Funds", "blocked by fraud check", or "rejected in fraud
    review").
  - PENDING with fraud decision REVIEW — waiting for a manual fraud
    review by FinCore staff; no money has moved yet. Staff either approve
    it (it then completes, or fails if funds are no longer enough) or
    reject it (it fails).
  - PROCESSING — the transfer is being settled and the outcome wasn't
    confirmed yet; the system finishes it automatically, usually within a
    minute or two. Retrying is not needed and won't send money twice.
- Resubmitting the same form after a network error doesn't send money
  twice (every submission carries a unique idempotency key).
- A transfer can't be cancelled or reversed by the customer once
  completed.

## Paying a merchant (payments)

- Pay → choose a source wallet, enter the merchant id (the merchant
  shares it), the amount and an optional note.
- The merchant must be active and the currency must match the wallet.
- Results: SUCCESS (paid), FAILED (with a reason, no money moved),
  CREATED with fraud decision REVIEW (waiting for manual review), or
  PROCESSING (being settled; finishes automatically).
- A payment waiting in fraud review that nobody decides within 15 minutes
  expires (status EXPIRED); no money moves.
- Only the merchant's owner can refund a payment, fully or partly, up to
  the amount not refunded yet. Refunds go back to the payer's wallet.
  Status becomes PARTIALLY_REFUNDED or REFUNDED. A payer can't refund
  their own payment; they have to ask the merchant.

## Fraud checks

Every transfer and payment is risk-scored before money moves:

- Amount above 500,000.00 (in the operation's currency): +30 points.
- The customer already had 5 or more operations checked in the last 60
  seconds: +25.
- The customer already had 3 or more operations sent to review or
  blocked in the last hour: +25.

Score 0–39 → ALLOW (goes ahead), 40–69 → REVIEW (waits for staff), 70 or
more → BLOCK (fails immediately with "blocked by fraud check"). One rule
alone never blocks or sends to review. Staff decisions on reviews are
final; the assistant can't approve, reject or speed them up.

## Merchants and webhooks

- Any customer can create a merchant (Merchants → Create merchant) and
  receive payments to it. The merchant page lists payments received and
  allows refunds.
- Webhooks: a merchant can register an https/http URL; FinCore POSTs
  payment events (payment.completed, payment.failed, payment.refunded)
  to it, signed with HMAC-SHA256 using the endpoint's secret. The secret
  is shown once, when the endpoint is created or the secret is rotated.
  Failed deliveries are retried with growing delays, up to 6 attempts; an
  endpoint is disabled automatically after 10 deliveries in a row fail,
  and its owner can re-enable it. Addresses on private or internal
  networks are rejected.

## Transaction history

History lists the transfers and payments the customer started, newest
first. Money received from others appears on the receiving wallet's
ledger entries, not in History.

## Security notes for customers

- FinCore staff never ask for a password. The assistant never needs one
  and must not be given one.
- The assistant can read the signed-in customer's own data to answer
  questions. It can't move money, change settings, or see other
  customers' data.

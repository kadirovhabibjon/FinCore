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
- Account → "Your details": the customer can edit their first name, last
  name, email address and phone number themselves and press "Save
  changes". Changing the email or the phone number asks for the current
  password (they are what the customer signs in with, and where a
  password reset code is sent); changing only the name does not. An
  email or phone that another account already uses is refused. After a
  change the customer signs in with the new email or phone; the old one
  stops working, and a notice is emailed to the previous email address.
  A new email address is not verified by a code, so a typo in it would
  send future reset codes to the wrong mailbox: suggest checking it.
- Passwords can be changed in Account → Password: it needs the current
  password, and the new one must differ. Changing the password signs out
  every other device; the device used stays signed in.
- Forgot password: on the sign-in page, "Forgot password?" → enter the
  phone number or email → a 6-digit code is emailed to the email address
  the account was registered with → enter the code and a new password
  (typed twice) → "Save new password". The code works once, for 10
  minutes, and stops working after 5 wrong tries; "Send a new code"
  emails another (at most 5 an hour). Resetting signs the account out on
  every device. For privacy the page never says whether an account
  exists for what was typed, so "no email arrived" can mean a typo, a
  different email on the account, or the spam folder. There is no reset
  by SMS, and a customer who no longer has access to that email address
  can't reset the password themselves.
- A reset code must never be shared: nobody at FinCore, and not this
  assistant, will ever ask for it. If a customer pastes one here, tell
  them not to and to request a new one.
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
- There is no fixed daily or per-operation amount limit: an operation
  needs a positive amount and enough available balance. Large or rapid
  operations can be held for fraud review or declined (see "Fraud
  checks"), so mention that whenever a customer asks about limits.
- There is no currency exchange: transfers and payments only work between
  wallets of the same currency.
- The wallets page shows reference exchange rates and a converter for
  about 160 currencies (from ExchangeRate-API, updated daily). They are
  for information only: FinCore does not convert money, and you cannot
  look up a rate yourself — point the customer to that section.

## Sending money (transfers)

- Every wallet has its own 16-digit FinCore card number starting with
  9955 (shown on the wallet, with a "Copy number" button on the wallet's
  page). It is what a customer gives someone to receive money. It is a
  FinCore number only: not a Visa, Mastercard, Uzcard or Humo card, it
  can't be used in shops, ATMs or other apps, and money can't be sent
  from FinCore to cards of other banks.
- Send → choose a source wallet, type the recipient's card number, check
  the name that appears (first name and last initial, for example
  "Aziza K."), then enter the amount and an optional note (up to 255
  characters). Send stays disabled until a recipient is found.
- If no name appears: a wrong digit is reported straight away; "no
  FinCore wallet can receive money at this card number" means the number
  isn't a wallet's or that wallet can't receive money right now.
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

History lists, newest first, the transfers and payments the customer
started and the transfers they received. Each transfer shows which way
the money went ("Sent" or "Received") and the other person's first name
and last initial. A transfer that failed or is waiting for review is
visible only to the sender: the recipient sees it once the money has
actually arrived. A merchant's received payments are on the merchant's
page, not in History.

## Notifications (the bell)

- The bell at the top of every page lists notifications, newest first,
  with a red badge showing how many are unread. Opening it marks them
  read.
- A notification is created when: someone sends the customer money
  ("Money received", with the sender's name and the amount); a transfer
  the customer sent completes ("Transfer completed") or fails ("Transfer
  failed", with the reason); a payment to a merchant completes ("Payment
  completed"), fails or expires ("Payment failed", no money taken); a
  merchant refunds a payment, fully or partly ("Refund received"); and,
  for a merchant's owner, when a customer pays that merchant ("Payment
  received").
- Announcements: FinCore staff can publish a message to every customer
  at once. It appears in the bell's Activity list like any notification
  and stays until staff withdraw it.
- The bell has two tabs. "Activity" is the customer's own notifications
  described above. "News" lists banking, finance and economy headlines
  collected automatically from public news feeds (the Central Bank of
  Uzbekistan, Spot.uz, Kun.uz, UzDaily), some in Uzbek and some in
  English. Clicking a headline opens it inside FinCore with the
  publisher's summary and a button that opens the full article on the
  publisher's site; "All news" lists everything kept. FinCore does not
  write, check or endorse these articles, and you cannot read or quote
  them yourself - point the customer to the News tab.
- Sign-ins do not create notifications in the bell. There are no SMS, email or phone push
  notifications: only the bell inside the web app, which checks for new
  ones every 15 seconds while a page is open.

## Security notes for customers

- FinCore staff never ask for a password. The assistant never needs one
  and must not be given one.
- The assistant can read the signed-in customer's own data to answer
  questions. It can't move money, change settings, or see other
  customers' data.

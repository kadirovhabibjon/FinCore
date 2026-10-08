from fastapi import status
from fincore_common import DomainError


class IdempotencyKeyInProgressError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Idempotency Key In Progress"


class IdempotencyKeyConflictError(DomainError):
    """The same Idempotency-Key was reused with a different request body
    — spec Section 9.1's "same key + different fingerprint" case.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Idempotency Key Conflict"


class InvalidAmountError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Amount"


class SameWalletTransferError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Same Wallet Transfer"


class CurrencyMismatchError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Currency Mismatch"


class WalletNotFoundError(DomainError):
    """Also covers "exists but isn't yours" — same anti-enumeration
    reasoning used throughout this project (e.g. ledger-service's own
    WalletNotFoundError, identity-service's InvalidCredentialsError).
    """

    status_code = status.HTTP_404_NOT_FOUND
    title = "Wallet Not Found"


class TransferNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Transfer Not Found"


class TransactionNotFoundError(DomainError):
    """Raised by `GET /api/v1/transactions/{id}` — distinct from
    TransferNotFoundError since this endpoint isn't transfer-specific
    (spec Section 20).
    """

    status_code = status.HTTP_404_NOT_FOUND
    title = "Transaction Not Found"


class MerchantNotFoundError(DomainError):
    """Also covers "exists but isn't yours" — same anti-enumeration
    reasoning as WalletNotFoundError.
    """

    status_code = status.HTTP_404_NOT_FOUND
    title = "Merchant Not Found"


class MerchantNotActiveError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Merchant Not Active"


class PaymentNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Payment Not Found"


class PaymentNotEligibleForRefundError(DomainError):
    """The payment isn't SUCCESS or PARTIALLY_REFUNDED (spec Section
    11's state machine) — refunding a PROCESSING, FAILED, EXPIRED, or
    already-fully-REFUNDED payment makes no sense.
    """

    status_code = status.HTTP_409_CONFLICT
    title = "Payment Not Eligible For Refund"


class InsufficientRoleError(DomainError):
    """The caller is authenticated but holds none of the roles the
    endpoint requires (the admin API, ADR-0005).
    """

    status_code = status.HTTP_403_FORBIDDEN
    title = "Insufficient Role"


class ReviewNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Review Not Found"


class ReviewAlreadyResolvedError(DomainError):
    """The operation exists but isn't awaiting review any more — another
    reviewer decided first, the payment expired, or it was never in
    REVIEW at all.
    """

    status_code = status.HTTP_409_CONFLICT
    title = "Review Already Resolved"


class RefundExceedsRemainingAmountError(DomainError):
    """spec Section 11: "total refunds <= captured amount." This is the
    fast-path check before the idempotency key is created; the
    `payments.ck_payments_refunded_amount_within_bounds` CHECK
    constraint is the actual race-safe guard (this project's "let the
    database decide" pattern).
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Refund Exceeds Remaining Amount"


class InvalidCardNumberError(DomainError):
    """Not a well-formed FinCore card number (16 digits, FinCore's
    prefix, valid check digit) - a typo, caught before any lookup."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Card Number"


class InvalidPhoneNumberError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Phone Number"


class InvalidRecipientQueryError(DomainError):
    """A recipient is looked up by a card number or by a phone number
    and currency - one or the other."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Recipient Query"


class RecipientNotFoundError(DomainError):
    """No wallet can receive money at this card number. One answer for
    "no such card", "wallet frozen or closed" and "owner's account not
    active": telling them apart would reveal an account's state to
    anyone who knows its card number."""

    status_code = status.HTTP_404_NOT_FOUND
    title = "Recipient Not Found"


class RecipientLookupUnavailableError(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Recipient Lookup Unavailable"


class MoneyRequestNotFoundError(DomainError):
    """Also covers a request the caller is not a party to."""

    status_code = status.HTTP_404_NOT_FOUND
    title = "Money Request Not Found"


class MoneyRequestNotOpenError(DomainError):
    """The request was already paid, declined or cancelled, or a payment
    for it is in progress."""

    status_code = status.HTTP_409_CONFLICT
    title = "Money Request Not Open"


class CannotRequestFromSelfError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Cannot Request From Yourself"


class TooManyOpenRequestsError(DomainError):
    """A cap on unanswered requests, so the feature can't be used to
    pester someone: a request puts a notification in another person's
    bell without their consent."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Too Many Open Requests"


class SameCurrencyExchangeError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Same Currency"


class AmountTooSmallError(DomainError):
    """The amount converts to less than one minor unit of the
    destination currency: there is nothing to give for it."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Amount Too Small"


class RateChangedError(DomainError):
    """The rate moved between the quote the customer saw and the
    exchange being made. Nothing was exchanged; a new quote is needed."""

    status_code = status.HTTP_409_CONFLICT
    title = "Rate Changed"


class ExchangeUnavailableError(DomainError):
    """No usable exchange rates, or ledger-service could not be asked
    for the accounts an exchange posts to. Nothing was exchanged."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Exchange Unavailable"


class ExchangeNotFoundError(DomainError):
    """Also covers "exists but isn't yours"."""

    status_code = status.HTTP_404_NOT_FOUND
    title = "Exchange Not Found"

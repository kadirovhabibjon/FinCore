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


class RefundExceedsRemainingAmountError(DomainError):
    """spec Section 11: "total refunds <= captured amount." This is the
    fast-path check before the idempotency key is created; the
    `payments.ck_payments_refunded_amount_within_bounds` CHECK
    constraint is the actual race-safe guard (this project's "let the
    database decide" pattern).
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Refund Exceeds Remaining Amount"

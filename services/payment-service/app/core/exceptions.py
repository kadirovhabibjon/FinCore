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

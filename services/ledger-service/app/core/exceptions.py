from fastapi import status
from fincore_common import DomainError


class UnbalancedPostingError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Unbalanced Posting"


class CurrencyMismatchError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Currency Mismatch"


class UnknownAccountError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Unknown Account"


class AccountNotActiveError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Account Not Active"


class InsufficientFundsError(DomainError):
    """A business rejection, not a bug: the caller (payment-service) is
    expected to catch this and move its own operation to FAILED — this is
    the "business rejection" branch of the transfer saga (spec Section
    10.1, ADR-0003), distinct from a timeout/5xx, which means "unknown."
    """

    status_code = status.HTTP_409_CONFLICT
    title = "Insufficient Funds"

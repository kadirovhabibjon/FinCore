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

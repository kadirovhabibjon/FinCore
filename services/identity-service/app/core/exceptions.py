from fastapi import status
from fincore_common import DomainError


class EmailAlreadyRegisteredError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Email Already Registered"


class PhoneAlreadyRegisteredError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Phone Already Registered"


class InvalidCredentialsError(DomainError):
    """Covers wrong password, unknown email, and non-ACTIVE accounts alike.

    Deliberately generic: distinguishing these cases in the response would
    let a caller enumerate registered emails or account statuses.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Invalid Credentials"


class InvalidTokenError(DomainError):
    """Missing, malformed, expired, or wrong-signature bearer token —
    also covers a token whose subject no longer maps to an active user.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Invalid Token"


class InsufficientRoleError(DomainError):
    """Authenticated, but without a role the endpoint requires (RBAC,
    spec Section 5)."""

    status_code = status.HTTP_403_FORBIDDEN
    title = "Insufficient Role"


class UserNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "User Not Found"


class SessionNotFoundError(DomainError):
    """Also covers "exists but isn't yours" — never reveals another
    user's session ids."""

    status_code = status.HTTP_404_NOT_FOUND
    title = "Session Not Found"


class CannotChangeOwnStatusError(DomainError):
    """An admin blocking or suspending their own account would lock the
    system out of the one role able to undo it."""

    status_code = status.HTTP_409_CONFLICT
    title = "Cannot Change Own Status"

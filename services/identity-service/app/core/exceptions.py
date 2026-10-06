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


class IncorrectPasswordError(DomainError):
    """The current password given to change it was wrong. 422, not 401:
    the caller is authenticated; a 401 here would read as "your session
    ended" and send a browser client off to sign in again.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Incorrect Password"


class PasswordUnchangedError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Password Unchanged"


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


class InvalidResetCodeError(DomainError):
    """The one answer to every failed password reset: no such account,
    no code requested, code expired or already used, too many wrong
    tries, or simply the wrong digits. Telling them apart would let a
    caller learn who has an account and how a guess is going."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Or Expired Code"

    def __init__(self) -> None:
        super().__init__("The code is wrong or has expired. Request a new one and try again.")


class PasswordResetUnavailableError(DomainError):
    """This deployment has no way to send email. Said to everyone alike,
    so it reveals nothing about any account."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Password Reset Unavailable"

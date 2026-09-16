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

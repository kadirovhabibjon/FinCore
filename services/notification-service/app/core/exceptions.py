from fastapi import status
from fincore_common import DomainError


class DeadLetterNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Dead Letter Not Found"


class AlreadyReplayedError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Already Replayed"


class NewsNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "News Not Found"


class AnnouncementNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Announcement Not Found"


class SupportThreadNotFoundError(DomainError):
    """This customer has never written to support."""

    status_code = status.HTTP_404_NOT_FOUND
    title = "Support Thread Not Found"


class TooManyMessagesError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Too Many Messages"


class InsufficientRoleError(DomainError):
    """Authenticated, but without a role the endpoint requires."""

    status_code = status.HTTP_403_FORBIDDEN
    title = "Insufficient Role"

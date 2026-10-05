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

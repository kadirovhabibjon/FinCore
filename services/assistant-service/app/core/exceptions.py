from fastapi import status
from fincore_common import DomainError


class AssistantNotConfiguredError(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Assistant Not Configured"


class AssistantUnavailableError(DomainError):
    """Claude API unreachable, rate-limited or erroring after the SDK's
    own retries."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Assistant Unavailable"


class ChatRateLimitedError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Too Many Messages"


class InvalidConversationError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Conversation"

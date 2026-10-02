from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError
from pydantic import BaseModel, Field

from app.core import auth
from app.core.config import settings
from app.core.exceptions import ChatRateLimitedError, InvalidConversationError
from app.services import assistant
from app.services.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

_bearer_scheme = HTTPBearer(auto_error=False)
limiter = SlidingWindowLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """The conversation so far, oldest first, ending with the customer's
    new message. The browser keeps the history; nothing is stored here."""

    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str


def _validate(messages: list[ChatMessage]) -> None:
    if len(messages) > settings.max_history_messages:
        raise InvalidConversationError(
            f"at most {settings.max_history_messages} messages per request"
        )
    for index, message in enumerate(messages):
        expected = "user" if index % 2 == 0 else "assistant"
        if message.role != expected:
            raise InvalidConversationError("messages must alternate, starting with the user")
        if len(message.content) > settings.max_message_chars:
            raise InvalidConversationError(
                f"each message must be at most {settings.max_message_chars} characters"
            )
    if messages[-1].role != "user":
        raise InvalidConversationError("the last message must be the user's")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> ChatResponse:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")
    claims = await auth.jwt_verifier.verify(credentials.credentials)
    user_id = str(UUID(claims["sub"]))

    _validate(payload.messages)
    if not limiter.allow(user_id):
        raise ChatRateLimitedError(
            f"Up to {settings.rate_limit_requests} messages per "
            f"{settings.rate_limit_window_seconds // 60} minutes. Please try again later."
        )

    reply = await assistant.answer(
        [assistant.ChatTurn(role=m.role, content=m.content) for m in payload.messages],
        bearer_token=credentials.credentials,
    )
    return ChatResponse(reply=reply)

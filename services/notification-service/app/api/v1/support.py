"""Writing to FinCore's staff, and staff answering.

Customers: /api/v1/support - their one conversation. Staff (SUPPORT and
ADMIN): /api/v1/admin/support - everyone's. Messages are plain text; no
markup or links are interpreted by any client.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.announcements import require_roles
from app.api.v1.notifications import get_current_user_id
from app.core.exceptions import SupportThreadNotFoundError
from app.db.session import get_db
from app.domain.support import SupportSender, SupportStatus, SupportThread
from app.services import support

router = APIRouter(prefix="/api/v1/support", tags=["support"])
admin_router = APIRouter(prefix="/api/v1/admin/support", tags=["admin"])

_staff = require_roles("SUPPORT", "ADMIN")


class PostMessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Who wrote it: the CUSTOMER or FinCore's STAFF.
    sender: SupportSender
    body: str
    created_at: datetime


class ConversationResponse(BaseModel):
    """The caller's conversation with staff. Before they have written
    anything: OPEN, nothing unread, no messages."""

    status: SupportStatus
    # Replies from staff the customer has not opened yet.
    unread_count: int
    items: list[MessageResponse]


class ThreadResponse(BaseModel):
    """A conversation as staff see it in the inbox."""

    user_id: UUID
    status: SupportStatus
    last_message_at: datetime
    last_sender: SupportSender
    # The start of the last message.
    last_body: str
    # Messages from the customer no staff member has opened yet.
    unread_count: int

    @classmethod
    def of(cls, thread: SupportThread) -> "ThreadResponse":
        return cls(
            user_id=thread.user_id,
            status=thread.status,
            last_message_at=thread.last_message_at,
            last_sender=thread.last_sender,
            last_body=thread.last_body,
            unread_count=thread.staff_unread,
        )


class InboxResponse(BaseModel):
    # Open conversations whose last word is the customer's.
    waiting_count: int
    # Messages from customers no staff member has opened yet, in all
    # conversations together (not only the ones listed).
    unread_count: int
    items: list[ThreadResponse]


class ThreadDetailResponse(ThreadResponse):
    items: list[MessageResponse]


# --- customers -----------------------------------------------------------


@router.get("/messages", response_model=ConversationResponse)
async def get_my_conversation(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """The caller's conversation with staff, oldest message first."""
    thread = await support.get_thread(session, user_id)
    messages = await support.list_messages(session, user_id)
    return ConversationResponse(
        status=thread.status if thread else SupportStatus.OPEN,
        unread_count=thread.customer_unread if thread else 0,
        items=[MessageResponse.model_validate(message) for message in messages],
    )


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def write_to_support(
    payload: PostMessageRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Writes to staff. At most 20 messages in ten minutes."""
    message = await support.post_from_customer(session, user_id, payload.body)
    return MessageResponse.model_validate(message)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_replies_read(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """The customer has opened the conversation. Idempotent."""
    await support.mark_read_by_customer(session, user_id)


# --- staff ---------------------------------------------------------------


@admin_router.get("/threads", response_model=InboxResponse)
async def list_threads(
    status: SupportStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> InboxResponse:
    """Every customer's conversation: open ones first, then by latest
    message. SUPPORT and ADMIN."""
    threads = await support.inbox(session, status=status, limit=limit, offset=offset)
    return InboxResponse(
        waiting_count=await support.waiting_count(session),
        unread_count=await support.unread_count(session),
        items=[ThreadResponse.of(thread) for thread in threads],
    )


async def _detail(session: AsyncSession, thread: SupportThread) -> ThreadDetailResponse:
    messages = await support.list_messages(session, thread.user_id)
    return ThreadDetailResponse(
        **ThreadResponse.of(thread).model_dump(),
        items=[MessageResponse.model_validate(message) for message in messages],
    )


@admin_router.get("/threads/{user_id}", response_model=ThreadDetailResponse)
async def get_thread(
    user_id: UUID,
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> ThreadDetailResponse:
    thread = await support.get_thread(session, user_id)
    if thread is None:
        raise SupportThreadNotFoundError(str(user_id))
    return await _detail(session, thread)


@admin_router.post("/threads/{user_id}/read", response_model=ThreadResponse)
async def mark_thread_read(
    user_id: UUID,
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """A staff member has opened the conversation. Idempotent."""
    return ThreadResponse.of(await support.mark_read_by_staff(session, user_id))


@admin_router.post(
    "/threads/{user_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reply(
    user_id: UUID,
    payload: PostMessageRequest,
    staff_user_id: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Replies to a customer who has written; they are told in their
    bell. A customer who never wrote can't be written to from here."""
    message = await support.post_from_staff(
        session, user_id, staff_user_id=staff_user_id, body=payload.body
    )
    return MessageResponse.model_validate(message)


@admin_router.post("/threads/{user_id}/resolve", response_model=ThreadResponse)
async def resolve_thread(
    user_id: UUID,
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Nothing left to answer. The customer writing again reopens it."""
    return ThreadResponse.of(await support.set_status(session, user_id, SupportStatus.RESOLVED))


@admin_router.post("/threads/{user_id}/reopen", response_model=ThreadResponse)
async def reopen_thread(
    user_id: UUID,
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    return ThreadResponse.of(await support.set_status(session, user_id, SupportStatus.OPEN))

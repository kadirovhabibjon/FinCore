"""A customer's conversation with FinCore's staff (app/domain/support.py).

Every write goes through the conversation's own row, locked first: a
message and the counters it changes land in one transaction, and two
people writing or reading at once take turns instead of losing a count.
"""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SupportThreadNotFoundError, TooManyMessagesError
from app.domain.notification import Notification
from app.domain.support import SupportMessage, SupportSender, SupportStatus, SupportThread

SUPPORT_REPLY = "support.reply"
_PREVIEW_LENGTH = 200
# A person typing, not a script: 20 messages in ten minutes is already a
# lot of typing, and staff reading the inbox are people too.
_CUSTOMER_LIMIT = 20
_CUSTOMER_WINDOW = timedelta(minutes=10)


def _preview(body: str) -> str:
    one_line = " ".join(body.split())
    if len(one_line) <= _PREVIEW_LENGTH:
        return one_line
    return one_line[: _PREVIEW_LENGTH - 1] + "…"


async def _locked_thread(session: AsyncSession, user_id: UUID) -> SupportThread | None:
    return await session.get(
        SupportThread, user_id, with_for_update=True, populate_existing=True
    )


async def list_messages(
    session: AsyncSession, user_id: UUID, *, limit: int = 200
) -> list[SupportMessage]:
    """The conversation's latest messages, oldest first."""
    result = await session.execute(
        select(SupportMessage)
        .where(SupportMessage.user_id == user_id)
        .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def post_from_customer(session: AsyncSession, user_id: UUID, body: str) -> SupportMessage:
    """The customer writes: starts the conversation if there is none,
    reopens it if staff had marked it resolved."""
    now = datetime.now(UTC)
    # Make sure the row exists, then lock it: a first message racing
    # another first message finds the row the other one made. Everything
    # the row says is set below, under the lock, whoever created it.
    await session.execute(
        insert(SupportThread)
        .values(
            user_id=user_id,
            status=SupportStatus.OPEN,
            last_message_at=now,
            last_sender=SupportSender.CUSTOMER,
            last_body=_preview(body),
            staff_unread=0,
        )
        .on_conflict_do_nothing(index_elements=[SupportThread.user_id])
    )
    thread = await _locked_thread(session, user_id)
    assert thread is not None  # inserted above, and threads are never deleted

    recent = await session.execute(
        select(func.count())
        .select_from(SupportMessage)
        .where(
            SupportMessage.user_id == user_id,
            SupportMessage.sender == SupportSender.CUSTOMER,
            SupportMessage.created_at > now - _CUSTOMER_WINDOW,
        )
    )
    if recent.scalar_one() >= _CUSTOMER_LIMIT:
        await session.rollback()
        raise TooManyMessagesError("Too many messages. Please wait a few minutes.")

    message = SupportMessage(
        id=uuid.uuid4(), user_id=user_id, sender=SupportSender.CUSTOMER, body=body, created_at=now
    )
    session.add(message)
    thread.status = SupportStatus.OPEN
    thread.last_message_at = now
    thread.last_sender = SupportSender.CUSTOMER
    thread.last_body = _preview(body)
    thread.staff_unread += 1
    await session.commit()
    return message


async def post_from_staff(
    session: AsyncSession, user_id: UUID, *, staff_user_id: UUID, body: str
) -> SupportMessage:
    """Staff reply in a conversation the customer started, and the
    customer is told in their bell (the same transaction: no reply
    without its notification, no notification without its reply)."""
    thread = await _locked_thread(session, user_id)
    if thread is None:
        raise SupportThreadNotFoundError(str(user_id))

    now = datetime.now(UTC)
    message = SupportMessage(
        id=uuid.uuid4(),
        user_id=user_id,
        sender=SupportSender.STAFF,
        staff_user_id=staff_user_id,
        body=body,
        created_at=now,
    )
    session.add(message)
    thread.last_message_at = now
    thread.last_sender = SupportSender.STAFF
    thread.last_body = _preview(body)
    thread.customer_unread += 1
    # Answering is reading.
    thread.staff_unread = 0
    session.add(
        Notification(
            # Not an event from Kafka: the message is its own unique source.
            event_id=message.id,
            recipient_user_id=user_id,
            notification_type=SUPPORT_REPLY,
            subject="Support replied",
            body=_preview(body),
            params={"preview": _preview(body)},
        )
    )
    await session.commit()
    return message


async def mark_read_by_customer(session: AsyncSession, user_id: UUID) -> None:
    thread = await _locked_thread(session, user_id)
    if thread is not None and thread.customer_unread:
        thread.customer_unread = 0
    await session.commit()


async def mark_read_by_staff(session: AsyncSession, user_id: UUID) -> SupportThread:
    thread = await _locked_thread(session, user_id)
    if thread is None:
        raise SupportThreadNotFoundError(str(user_id))
    thread.staff_unread = 0
    await session.commit()
    await session.refresh(thread)
    return thread


async def set_status(session: AsyncSession, user_id: UUID, status: SupportStatus) -> SupportThread:
    thread = await _locked_thread(session, user_id)
    if thread is None:
        raise SupportThreadNotFoundError(str(user_id))
    thread.status = status
    if status is SupportStatus.RESOLVED:
        thread.staff_unread = 0
    await session.commit()
    await session.refresh(thread)
    return thread


async def get_thread(session: AsyncSession, user_id: UUID) -> SupportThread | None:
    return await session.get(SupportThread, user_id)


async def inbox(
    session: AsyncSession, *, status: SupportStatus | None, limit: int, offset: int
) -> list[SupportThread]:
    """Conversations for staff: open ones first, then by latest message."""
    statement = select(SupportThread)
    if status is not None:
        statement = statement.where(SupportThread.status == status)
    result = await session.execute(
        statement.order_by(
            (SupportThread.status == SupportStatus.OPEN).desc(),
            SupportThread.last_message_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def unread_count(session: AsyncSession) -> int:
    """Messages from customers that no staff member has opened yet,
    across every conversation."""
    result = await session.execute(select(func.coalesce(func.sum(SupportThread.staff_unread), 0)))
    return int(result.scalar_one())


async def waiting_count(session: AsyncSession) -> int:
    """Open conversations whose last word is the customer's."""
    result = await session.execute(
        select(func.count())
        .select_from(SupportThread)
        .where(
            SupportThread.status == SupportStatus.OPEN,
            SupportThread.last_sender == SupportSender.CUSTOMER,
        )
    )
    return int(result.scalar_one())

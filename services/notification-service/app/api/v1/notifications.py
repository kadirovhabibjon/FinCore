from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.db.session import get_db
from app.domain.announcement import Announcement
from app.domain.notification import Notification
from app.repositories.announcement_repository import AnnouncementRepository
from app.repositories.notification_repository import NotificationRepository

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID:
    """Reads `auth.jwt_verifier` at call time so tests can swap it."""
    if credentials is None:
        raise InvalidTokenError("missing bearer token")
    payload = await auth.jwt_verifier.verify(credentials.credentials)
    return UUID(payload["sub"])


ANNOUNCEMENT = "announcement"


class NotificationResponse(BaseModel):
    id: UUID
    # What happened: "transfer.completed", "transfer.failed",
    # "transfer.received", "payment.completed", "payment.failed",
    # "payment.refunded", "payment.received", or "announcement" (a
    # message from FinCore to every customer).
    type: str
    # English text, ready to show.
    title: str
    body: str
    # The facts the text was built from (amount, counterparty,
    # reference, reason, partial), for showing it in another language.
    # Null for announcements and for notifications older than this field.
    params: dict[str, Any] | None
    created_at: datetime
    read: bool

    @classmethod
    def of(cls, notification: Notification) -> "NotificationResponse":
        return cls(
            id=notification.id,
            type=notification.notification_type,
            title=notification.subject,
            body=notification.body,
            params=notification.params,
            created_at=notification.created_at,
            read=notification.read_at is not None,
        )

    @classmethod
    def of_announcement(
        cls, announcement: Announcement, *, seen_at: datetime
    ) -> "NotificationResponse":
        return cls(
            id=announcement.id,
            type=ANNOUNCEMENT,
            title=announcement.title,
            body=announcement.body,
            params=None,
            created_at=announcement.created_at,
            read=announcement.created_at <= seen_at,
        )


class NotificationListResponse(BaseModel):
    """One request serves the bell: the badge and the list under it."""

    unread_count: int
    items: list[NotificationResponse]


@router.get("", response_model=NotificationListResponse)
async def list_my_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """The caller's own notifications together with FinCore's
    announcements to everyone, newest first, and how many of all of
    them are unread.

    The two are merged here rather than in SQL: they live in different
    tables with different read tracking (per notification, and one
    "last looked" moment per customer for announcements), and both are
    read newest-first up to the end of the requested page.
    """
    notifications = NotificationRepository(session)
    announcements = AnnouncementRepository(session)
    seen_at = await announcements.seen_at(user_id)
    upto = offset + limit
    merged = [
        NotificationResponse.of(item)
        for item in await notifications.list_for_user(user_id, limit=upto, offset=0)
    ] + [
        NotificationResponse.of_announcement(item, seen_at=seen_at)
        for item in await announcements.list_recent(limit=upto)
    ]
    merged.sort(key=lambda item: item.created_at, reverse=True)
    return NotificationListResponse(
        unread_count=await notifications.count_unread(user_id)
        + await announcements.count_since(seen_at),
        items=merged[offset:upto],
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_my_notifications_read(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Marks every unread notification of the caller read, and every
    announcement so far seen (opening the bell). Idempotent."""
    await NotificationRepository(session).mark_all_read(user_id)
    await AnnouncementRepository(session).mark_seen(user_id)
    await session.commit()

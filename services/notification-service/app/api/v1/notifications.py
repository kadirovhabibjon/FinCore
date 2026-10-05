from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.db.session import get_db
from app.domain.notification import Notification
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


class NotificationResponse(BaseModel):
    id: UUID
    # "transfer.completed", "transfer.failed" or "transfer.received".
    type: str
    title: str
    body: str
    created_at: datetime
    read: bool

    @classmethod
    def of(cls, notification: Notification) -> "NotificationResponse":
        return cls(
            id=notification.id,
            type=notification.notification_type,
            title=notification.subject,
            body=notification.body,
            created_at=notification.created_at,
            read=notification.read_at is not None,
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
    """The caller's own notifications, newest first, and how many of all
    of them are unread."""
    repository = NotificationRepository(session)
    items = await repository.list_for_user(user_id, limit=limit, offset=offset)
    return NotificationListResponse(
        unread_count=await repository.count_unread(user_id),
        items=[NotificationResponse.of(item) for item in items],
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_my_notifications_read(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Marks every unread notification of the caller read (opening the
    bell). Idempotent."""
    await NotificationRepository(session).mark_all_read(user_id)
    await session.commit()

"""Staff side of announcements: an ADMIN writes a message that every
customer finds in their bell. Customers read them through
GET /api/v1/notifications, not here."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.core.exceptions import AnnouncementNotFoundError, InsufficientRoleError
from app.db.session import get_db
from app.domain.announcement import Announcement
from app.repositories.announcement_repository import AnnouncementRepository

router = APIRouter(prefix="/api/v1/admin/announcements", tags=["admin"])

_bearer_scheme = HTTPBearer(auto_error=False)


def require_roles(*allowed: str) -> Callable[..., Awaitable[UUID]]:
    """Role check from the token's `roles` claim, as payment-service's
    admin API does: this service can only trust the signed claim, so a
    revoked role keeps working until that access token expires."""

    async def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> UUID:
        if credentials is None:
            raise InvalidTokenError("missing bearer token")
        payload = await auth.jwt_verifier.verify(credentials.credentials)
        if not set(payload.get("roles") or ()).intersection(allowed):
            raise InsufficientRoleError(f"requires one of: {', '.join(allowed)}")
        return UUID(payload["sub"])

    return _dependency


_staff = require_roles("SUPPORT", "ADMIN")
_admin = require_roles("ADMIN")


class CreateAnnouncementRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("title", "body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    created_by_user_id: UUID
    created_at: datetime


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def publish_announcement(
    payload: CreateAnnouncementRequest,
    admin_id: UUID = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> AnnouncementResponse:
    """Publishes a message to every customer at once. ADMIN only. Shown
    as plain text: no markup or links are interpreted."""
    announcement = Announcement(
        title=payload.title, body=payload.body, created_by_user_id=admin_id
    )
    AnnouncementRepository(session).add(announcement)
    await session.commit()
    await session.refresh(announcement)
    return AnnouncementResponse.model_validate(announcement)


@router.get("", response_model=list[AnnouncementResponse])
async def list_announcements(
    limit: int = Query(default=50, ge=1, le=200),
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[AnnouncementResponse]:
    """Published announcements, newest first. SUPPORT and ADMIN."""
    items = await AnnouncementRepository(session).list_recent(limit=limit)
    return [AnnouncementResponse.model_validate(item) for item in items]


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_announcement(
    announcement_id: UUID,
    _: UUID = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Withdraws an announcement: it disappears from every bell. ADMIN only."""
    announcement = await AnnouncementRepository(session).get(announcement_id)
    if announcement is None:
        raise AnnouncementNotFoundError(str(announcement_id))
    announcement.deleted_at = datetime.now(UTC)
    await session.commit()

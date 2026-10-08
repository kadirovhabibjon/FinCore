from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthContext, require_roles
from app.api.v1.schemas import AdminUserResponse, UserResponse, UserStatusUpdateRequest
from app.core.exceptions import UserNotFoundError
from app.db.session import get_db
from app.domain.role import RoleName
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services.user_admin import change_user_status

# ADR-0005's support/admin panel. SUPPORT can look users up; only ADMIN
# can change an account's status.
router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])

_staff = require_roles(RoleName.SUPPORT, RoleName.ADMIN)
_admin = require_roles(RoleName.ADMIN)


def _with_roles(user: User, roles: list[str]) -> AdminUserResponse:
    profile = UserResponse.model_validate(user).model_dump()
    return AdminUserResponse(**profile, roles=sorted(roles))


@router.get("", response_model=list[AdminUserResponse])
async def search_users(
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthContext = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    repository = UserRepository(session)
    users = await repository.search(q, limit=limit, offset=offset)
    roles = await repository.get_role_names_for([user.id for user in users])
    return [_with_roles(user, roles[user.id]) for user in users]


class RegistrationsDay(BaseModel):
    # A calendar day in UTC.
    date: date
    registered: int


class UserStatsResponse(BaseModel):
    # Every account there is.
    total: int
    # How many are in each status; a status nobody is in is absent.
    by_status: dict[str, int]
    # One entry per day, oldest first, zeros included.
    days: list[RegistrationsDay]


# Declared before /{user_id}, which would otherwise capture "stats".
@router.get("/stats", response_model=UserStatsResponse)
async def get_user_stats(
    days: int = Query(default=14, ge=1, le=90),
    _: AuthContext = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """How many accounts there are, by status, and how many were created
    on each of the last `days` days (UTC). SUPPORT and ADMIN."""
    repository = UserRepository(session)
    today = datetime.now(UTC).date()
    keys = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    registered = await repository.registrations_per_day(
        datetime.combine(keys[0], datetime.min.time(), tzinfo=UTC)
    )
    by_status = await repository.count_by_status()
    return UserStatsResponse(
        total=sum(by_status.values()),
        by_status=by_status,
        days=[RegistrationsDay(date=key, registered=registered.get(key, 0)) for key in keys],
    )


@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_user(
    user_id: UUID,
    _: AuthContext = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    repository = UserRepository(session)
    user = await repository.get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))
    return _with_roles(user, await repository.get_role_names(user.id))


@router.post("/{user_id}/status", response_model=AdminUserResponse)
async def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    context: AuthContext = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await change_user_status(
        session, actor_id=context.user.id, user_id=user_id, new_status=payload.status
    )
    return _with_roles(user, await UserRepository(session).get_role_names(user.id))

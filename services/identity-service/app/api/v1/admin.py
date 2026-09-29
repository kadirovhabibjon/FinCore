from uuid import UUID

from fastapi import APIRouter, Depends, Query
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

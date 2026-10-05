import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fincore_common import InvalidInternalTokenError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UserNotFoundError
from app.db.session import get_db
from app.domain.user import UserStatus
from app.repositories.user_repository import UserRepository


async def require_internal_service(x_internal_token: str = Header(...)) -> None:
    """Reads the setting per request (tests change it) and fails closed:
    with no token configured, nothing matches."""
    expected = settings.internal_service_token
    if not expected or not hmac.compare_digest(x_internal_token.encode(), expected.encode()):
        raise InvalidInternalTokenError("internal service token mismatch")


router = APIRouter(
    prefix="/internal/v1/users",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


class InternalUserResponse(BaseModel):
    """The little another service may know about a user: who they are
    by name and whether the account is usable. No email, phone or roles."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    status: UserStatus


@router.get("/{user_id}", response_model=InternalUserResponse)
async def get_user(user_id: UUID, session: AsyncSession = Depends(get_db)) -> InternalUserResponse:
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))
    return InternalUserResponse.model_validate(user)

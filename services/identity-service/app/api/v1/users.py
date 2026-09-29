from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthContext, get_auth_context
from app.api.v1.schemas import CurrentUserResponse, SessionResponse, UserResponse
from app.core.exceptions import SessionNotFoundError
from app.db.session import get_db
from app.services.sessions import list_active_sessions, revoke_user_session

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=CurrentUserResponse)
async def read_current_user(
    context: AuthContext = Depends(get_auth_context),
) -> CurrentUserResponse:
    profile = UserResponse.model_validate(context.user).model_dump()
    return CurrentUserResponse(**profile, roles=sorted(context.roles))


@router.get("/me/sessions", response_model=list[SessionResponse])
async def list_my_sessions(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """The caller's refreshable sessions (ADR-0005: "view/revoke active
    sessions"), most recently used first, with the one this request's
    token came from marked `current`."""
    sessions = await list_active_sessions(session, context.user.id)
    return [
        SessionResponse.model_validate(s).model_copy(
            update={"current": s.id == context.session_id}
        )
        for s in sessions
    ]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_session(
    session_id: UUID,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Revokes one of the caller's own sessions — every refresh token it
    will ever issue stops working. An access token already issued from it
    stays valid until it expires (short-lived by design). Revoking the
    current session is allowed: that's a remote logout of this device."""
    if not await revoke_user_session(session, context.user.id, session_id):
        raise SessionNotFoundError(str(session_id))

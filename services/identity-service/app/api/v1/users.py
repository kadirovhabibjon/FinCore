from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthContext, get_auth_context
from app.api.v1.schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    SessionResponse,
    TwoFactorChallengeResponse,
    TwoFactorPasswordRequest,
    UpdateProfileRequest,
    UserResponse,
    VerifyLoginRequest,
)
from app.core.exceptions import SessionNotFoundError
from app.db.session import get_db
from app.services import mailer, two_factor
from app.services.password import change_password
from app.services.profile import update_profile
from app.services.sessions import list_active_sessions, revoke_user_session

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=CurrentUserResponse)
async def read_current_user(
    context: AuthContext = Depends(get_auth_context),
) -> CurrentUserResponse:
    return _me(context)


def _me(context: AuthContext) -> CurrentUserResponse:
    profile = UserResponse.model_validate(context.user).model_dump()
    return CurrentUserResponse(
        **profile,
        roles=sorted(context.roles),
        two_factor_enabled=context.user.two_factor_enabled,
    )


@router.patch("/me", response_model=CurrentUserResponse)
async def update_my_profile(
    payload: UpdateProfileRequest,
    background: BackgroundTasks,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Edits the caller's own name, email address or phone number; only
    the fields sent, and only those that differ, change. A new email or
    phone needs `current_password` (they are how the account is signed
    in to and recovered) and must be unused. The account's previous
    email address is told about such a change."""
    change = await update_profile(
        session,
        context.user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        current_password=payload.current_password,
    )
    what = " and ".join(
        label
        for field, label in (("email", "email address"), ("phone", "phone number"))
        if field in change.changed
    )
    if what and mailer.is_configured():
        background.add_task(
            mailer.send_contact_changed,
            to=change.previous_email,
            first_name=context.user.first_name,
            what=what,
        )
    return _me(context)


@router.post(
    "/me/two-factor/enable",
    response_model=TwoFactorChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def begin_two_factor(
    payload: TwoFactorPasswordRequest,
    background: BackgroundTasks,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> TwoFactorChallengeResponse:
    """First half of turning two-step sign-in on: checks the password
    and emails a code. Nothing changes until that code is confirmed -
    an account is never put behind a mailbox that hasn't been shown to
    work. `503` if no code can be emailed to this account."""
    challenge = await two_factor.begin_enabling(session, context.user, payload.current_password)
    background.add_task(
        mailer.send_login_code,
        to=challenge.email,
        first_name=challenge.first_name,
        code=challenge.code,
        enabling=True,
    )
    return TwoFactorChallengeResponse(
        challenge_id=challenge.id,
        email_hint=two_factor.email_hint(challenge.email),
        expires_in=challenge.expires_in,
    )


@router.post("/me/two-factor/confirm", response_model=CurrentUserResponse)
async def confirm_two_factor(
    payload: VerifyLoginRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Second half: the emailed code turns two-step sign-in on. From
    the next sign-in, the password alone is not enough."""
    await two_factor.confirm_enabling(
        session, context.user, payload.challenge_id, payload.code
    )
    return _me(context)


@router.post("/me/two-factor/disable", response_model=CurrentUserResponse)
async def disable_two_factor(
    payload: TwoFactorPasswordRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Turns two-step sign-in off. Needs the current password."""
    await two_factor.disable(session, context.user, payload.current_password)
    return _me(context)


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


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    payload: ChangePasswordRequest,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Requires the current password even though the caller is signed in,
    so a borrowed unlocked device can't lock the owner out. Signs out
    every other session; this one stays."""
    await change_password(
        session,
        context.user,
        current_session_id=context.session_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )

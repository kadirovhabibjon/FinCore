from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import settings
from app.core.exceptions import (
    InsufficientRoleError,
    InvalidTokenError,
    PasswordResetUnavailableError,
)
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.domain.role import RoleName
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services import mailer
from app.services.authentication import authenticate_user
from app.services.password_reset import confirm_reset, request_reset
from app.services.registration import RegistrationData, register_user
from app.services.sessions import (
    IssuedRefreshToken,
    revoke_session_by_refresh_token,
    revoke_user_session,
    rotate_refresh_token,
    start_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ADR-0006: a browser client sends this header to receive the refresh
# token as an httpOnly cookie instead of in the JSON body. Requiring a
# custom header (not just the cookie) is a CSRF defense on top of
# SameSite=Strict: a cross-site page can't attach it without a CORS
# preflight the gateway never approves.
#
# Two values, two independent sessions in one browser: "cookie" for the
# customer site and "cookie-admin" for the admin console, each with its
# own cookie. Signing in to (or out of) one never signs you in to (or
# out of) the other, and an admin-console session is only ever issued to
# a staff account.
_CUSTOMER_TRANSPORT = "cookie"
_ADMIN_TRANSPORT = "cookie-admin"
_STAFF_ROLES = {RoleName.SUPPORT.value, RoleName.ADMIN.value}


def _cookie_name(transport: str | None) -> str | None:
    """The refresh cookie this request uses, or None for body transport."""
    if transport == _CUSTOMER_TRANSPORT:
        return settings.refresh_cookie_name
    if transport == _ADMIN_TRANSPORT:
        return f"{settings.refresh_cookie_name}_admin"
    return None


def _client_ip(request: Request) -> str | None:
    # The gateway sets X-Real-IP; without it (direct access in dev),
    # fall back to the socket peer.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def _set_refresh_cookie(response: Response, issued: IssuedRefreshToken, name: str) -> None:
    max_age = int((issued.expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        key=name,
        value=issued.token,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        key=name,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _presented_refresh_token(
    request: Request, payload: RefreshRequest | LogoutRequest | None, cookie: str | None
) -> str | None:
    if payload is not None:
        return payload.refresh_token
    if cookie is not None:
        return request.cookies.get(cookie)
    return None


async def _token_response(
    session: AsyncSession,
    issued: IssuedRefreshToken,
    response: Response,
    cookie: str | None,
    roles: list[str],
) -> TokenResponse:
    access_token, access_expires_at = create_access_token(
        issued.user_id, roles, session_id=issued.session_id
    )
    if cookie is not None:
        _set_refresh_cookie(response, issued, cookie)
    return TokenResponse(
        access_token=access_token,
        refresh_token=None if cookie is not None else issued.token,
        expires_in=int((access_expires_at - datetime.now(UTC)).total_seconds()),
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> User:
    return await register_user(
        session,
        RegistrationData(
            email=payload.email,
            phone=payload.phone,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    transport: str | None = Header(default=None, alias="X-Refresh-Token-Transport"),
) -> TokenResponse:
    user = await authenticate_user(session, payload.email, payload.password, phone=payload.phone)
    roles = await UserRepository(session).get_role_names(user.id)
    if transport == _ADMIN_TRANSPORT and _STAFF_ROLES.isdisjoint(roles):
        # Checked before a session exists, so a customer account gets no
        # admin-console session at all, not one the console then refuses.
        raise InsufficientRoleError("the admin console is for staff accounts only")
    issued = await start_session(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return await _token_response(session, issued, response, _cookie_name(transport), roles)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db),
    transport: str | None = Header(default=None, alias="X-Refresh-Token-Transport"),
) -> TokenResponse:
    cookie = _cookie_name(transport)
    presented = _presented_refresh_token(request, payload, cookie)
    if presented is None:
        raise InvalidTokenError("missing refresh token")
    # On failure the cookie is left in place: the token it holds is
    # already dead server-side (rotated, revoked or expired), so the
    # browser replaying it just gets this same 401 again. Logout clears it.
    issued = await rotate_refresh_token(session, presented)
    roles = await UserRepository(session).get_role_names(issued.user_id)
    if transport == _ADMIN_TRANSPORT and _STAFF_ROLES.isdisjoint(roles):
        # Staff role revoked since sign-in: end the console session.
        await revoke_user_session(session, issued.user_id, issued.session_id)
        raise InvalidTokenError("this account no longer has staff access")
    return await _token_response(session, issued, response, cookie, roles)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db),
    transport: str | None = Header(default=None, alias="X-Refresh-Token-Transport"),
) -> None:
    cookie = _cookie_name(transport)
    presented = _presented_refresh_token(request, payload, cookie)
    if presented is not None:
        await revoke_session_by_refresh_token(session, presented)
    if cookie is not None:
        _clear_refresh_cookie(response, cookie)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: PasswordResetRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Emails a 6-digit reset code to the account's address, if there is
    such an account. Always 202 with no body: the answer, and how long it
    takes, is the same whether or not the account exists (the email goes
    out after the response)."""
    if not mailer.is_configured():
        raise PasswordResetUnavailableError(
            "Password reset by email isn't set up on this server."
        )
    issued = await request_reset(session, email=payload.email, phone=payload.phone)
    if issued is not None:
        background.add_task(
            mailer.send_reset_code, to=issued.email, first_name=issued.first_name, code=issued.code
        )


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Sets a new password using the emailed code, and signs the account
    out everywhere. Any failure is the same 422."""
    await confirm_reset(
        session,
        email=payload.email,
        phone=payload.phone,
        code=payload.code,
        new_password=payload.new_password,
    )

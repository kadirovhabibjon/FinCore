from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services.authentication import authenticate_user
from app.services.registration import RegistrationData, register_user
from app.services.sessions import (
    IssuedRefreshToken,
    revoke_session_by_refresh_token,
    rotate_refresh_token,
    start_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ADR-0006: a browser client sends this header to receive the refresh
# token as an httpOnly cookie instead of in the JSON body. Requiring a
# custom header (not just the cookie) is a CSRF defense on top of
# SameSite=Strict: a cross-site page can't attach it without a CORS
# preflight the gateway never approves.
_COOKIE_TRANSPORT = "cookie"


def _wants_cookie(transport: str | None) -> bool:
    return transport == _COOKIE_TRANSPORT


def _client_ip(request: Request) -> str | None:
    # The gateway sets X-Real-IP; without it (direct access in dev),
    # fall back to the socket peer.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def _set_refresh_cookie(response: Response, issued: IssuedRefreshToken) -> None:
    max_age = int((issued.expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=issued.token,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _presented_refresh_token(
    request: Request, payload: RefreshRequest | LogoutRequest | None, cookie_mode: bool
) -> str | None:
    if payload is not None:
        return payload.refresh_token
    if cookie_mode:
        return request.cookies.get(settings.refresh_cookie_name)
    return None


async def _token_response(
    session: AsyncSession, issued: IssuedRefreshToken, response: Response, cookie_mode: bool
) -> TokenResponse:
    roles = await UserRepository(session).get_role_names(issued.user_id)
    access_token, access_expires_at = create_access_token(
        issued.user_id, roles, session_id=issued.session_id
    )
    if cookie_mode:
        _set_refresh_cookie(response, issued)
    return TokenResponse(
        access_token=access_token,
        refresh_token=None if cookie_mode else issued.token,
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
    user = await authenticate_user(session, payload.email, payload.password)
    issued = await start_session(
        session,
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return await _token_response(session, issued, response, _wants_cookie(transport))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db),
    transport: str | None = Header(default=None, alias="X-Refresh-Token-Transport"),
) -> TokenResponse:
    cookie_mode = _wants_cookie(transport)
    presented = _presented_refresh_token(request, payload, cookie_mode)
    if presented is None:
        raise InvalidTokenError("missing refresh token")
    # On failure the cookie is left in place: the token it holds is
    # already dead server-side (rotated, revoked or expired), so the
    # browser replaying it just gets this same 401 again. Logout clears it.
    issued = await rotate_refresh_token(session, presented)
    return await _token_response(session, issued, response, cookie_mode)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db),
    transport: str | None = Header(default=None, alias="X-Refresh-Token-Transport"),
) -> None:
    cookie_mode = _wants_cookie(transport)
    presented = _presented_refresh_token(request, payload, cookie_mode)
    if presented is not None:
        await revoke_session_by_refresh_token(session, presented)
    if cookie_mode:
        _clear_refresh_cookie(response)

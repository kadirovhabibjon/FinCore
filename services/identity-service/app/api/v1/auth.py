from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services.authentication import authenticate_user
from app.services.registration import RegistrationData, register_user
from app.services.sessions import (
    revoke_session_by_refresh_token,
    rotate_refresh_token,
    start_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await authenticate_user(session, payload.email, payload.password)
    roles = await UserRepository(session).get_role_names(user.id)

    access_token, access_expires_at = create_access_token(user.id, roles)
    issued_refresh = await start_session(session, user.id)

    return _token_response(access_token, access_expires_at, issued_refresh.token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    issued_refresh = await rotate_refresh_token(session, payload.refresh_token)
    roles = await UserRepository(session).get_role_names(issued_refresh.user_id)

    access_token, access_expires_at = create_access_token(issued_refresh.user_id, roles)

    return _token_response(access_token, access_expires_at, issued_refresh.token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> None:
    await revoke_session_by_refresh_token(session, payload.refresh_token)


def _token_response(
    access_token: str, access_expires_at: datetime, refresh_token: str
) -> TokenResponse:
    expires_in = int((access_expires_at - datetime.now(timezone.utc)).total_seconds())
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )

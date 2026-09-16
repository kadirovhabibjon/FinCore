from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services.authentication import authenticate_user
from app.services.registration import RegistrationData, register_user

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

    token, expires_at = create_access_token(user.id, roles)
    expires_in = int((expires_at - datetime.now(timezone.utc)).total_seconds())

    return TokenResponse(access_token=token, expires_in=expires_in)

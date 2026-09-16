from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import RegisterRequest, UserResponse
from app.db.session import get_db
from app.domain.user import User
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
